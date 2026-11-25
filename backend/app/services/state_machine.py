"""Persistent production state machine (spec 31)."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval, Project, StateTransition

ORDER = [
    "DRAFT", "RESEARCH_READY", "CONCEPT_READY", "CONCEPT_APPROVED", "SELECTING_PROVIDERS",
    "GENERATING_OR_IMPORTING_IMAGES", "IMAGE_REVIEW", "IMAGE_APPROVED", "BUILDING_ANIMATION",
    "GENERATING_OR_IMPORTING_AUDIO", "BUILDING_MASTERS", "PREVIEW_READY", "PREVIEW_APPROVED", "RENDERING",
    "QUALITY_CHECK", "FINAL_REVIEW", "APPROVED", "READY_FOR_UPLOAD", "UPLOADING_PRIVATE", "UPLOADED_PRIVATE",
    "PUBLISH_APPROVED", "SCHEDULED", "PUBLISHED",
]
SIDE = {"FAILED", "CANCELLED", "PAUSED", "ARCHIVED"}

# Explicit backward edges (regeneration / invalidation) on top of forward progress.
BACKWARD_OK = {
    "IMAGE_REVIEW", "IMAGE_APPROVED", "PREVIEW_READY", "BUILDING_MASTERS", "GENERATING_OR_IMPORTING_IMAGES",
    "FINAL_REVIEW", "QUALITY_CHECK", "RENDERING", "PREVIEW_APPROVED",
}
# States that only a human approval may enter.
HUMAN_ONLY = {"CONCEPT_APPROVED", "IMAGE_APPROVED", "PREVIEW_APPROVED", "APPROVED", "PUBLISH_APPROVED"}


class TransitionError(Exception):
    pass


def idx(state: str) -> int:
    return ORDER.index(state) if state in ORDER else -1


def at_least(project: Project, state: str) -> bool:
    return idx(project.state) >= idx(state)


def transition(db: Session, project: Project, to: str, actor: str = "system", note: str | None = None):
    frm = project.state
    if to == frm:
        return
    if to not in ORDER and to not in SIDE:
        raise TransitionError(f"Unknown state {to}")
    if to in HUMAN_ONLY and actor != "user" and (frm not in ORDER or idx(to) > idx(frm)):
        raise TransitionError(f"{to} requires a human approval")
    if frm in ("ARCHIVED", "CANCELLED") and to not in ("DRAFT", "CONCEPT_APPROVED"):
        raise TransitionError(f"Project is {frm}; restore it first")
    if to in ORDER and frm in ORDER and idx(to) < idx(frm) and to not in BACKWARD_OK:
        raise TransitionError(f"Cannot move back from {frm} to {to}")
    project.state = to
    db.add(StateTransition(project_id=project.id, from_state=frm, to_state=to, actor=actor, note=note))
    db.flush()


def config_hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:16]


def preview_hash(project: Project) -> str:
    d = project.data
    return config_hash(d.get("approved_image_asset_id"), d.get("animation"), d.get("audio"))


def approve(db: Session, project: Project, stage: str, decision: str, note: str | None, chash: str | None):
    db.add(Approval(project_id=project.id, stage=stage, decision=decision, config_hash=chash, note=note))
    db.flush()


def valid_approval(db: Session, project: Project, stage: str, chash: str | None = None) -> Approval | None:
    q = select(Approval).where(Approval.project_id == project.id, Approval.stage == stage, Approval.valid.is_(True),
                               Approval.decision == "approved").order_by(Approval.id.desc())
    a = db.scalars(q).first()
    if a and chash is not None and a.config_hash != chash:
        return None
    return a


def invalidate_from(db: Session, project: Project, stage: str, reason: str):
    """Underlying asset/config changed: invalidate this approval and all downstream ones."""
    chain = ["image", "preview", "final", "publish"]
    stages = chain[chain.index(stage):] if stage in chain else [stage]
    for a in db.scalars(select(Approval).where(Approval.project_id == project.id, Approval.stage.in_(stages),
                                               Approval.valid.is_(True))):
        a.valid = False
        a.note = (a.note or "") + f" [invalidated: {reason}]"
    target = {"image": "IMAGE_REVIEW", "preview": "IMAGE_APPROVED"}.get(stage)
    if target and idx(project.state) > idx(target) and project.state not in ("UPLOADED_PRIVATE", "PUBLISHED", "SCHEDULED"):
        project.state, frm = target, project.state
        db.add(StateTransition(project_id=project.id, from_state=frm, to_state=target, actor="system",
                               note=f"Invalidated: {reason}"))
