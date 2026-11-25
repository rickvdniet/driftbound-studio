"""Worker process: `python -m app.workers.worker`. Claims jobs from the DB queue and runs them.

Concurrency: run several workers for parallel jobs (render.concurrency setting is advisory; each worker runs one job).
"""
import logging
import signal
import time
import traceback
from datetime import datetime, timezone

from app.config.settings import get_settings
from app.db import migrate, session
from app.logging_setup import setup_logging
from app.models import Job, Project
from app.services.pipeline import TASKS
from app.workers.queue import Cancelled, JobContext, claim_next, recover_stale

log = logging.getLogger("driftbound.worker")
_stop = False


def run_one(job_id: int) -> str:
    with session() as db:
        j = db.get(Job, job_id)
        typ, pid, payload = j.type, j.project_id, dict(j.payload)
    log.info("job start", extra={"job": job_id, "type": typ, "project": pid})
    ctx = JobContext(job_id)
    status, result, error = "done", None, None
    try:
        handler = TASKS.get(typ)
        if not handler:
            raise RuntimeError(f"unknown job type {typ}")
        result = handler(ctx, pid, payload)
    except Cancelled:
        status, error = "cancelled", "Cancelled by user"
    except Exception as e:
        status, error = "failed", f"{type(e).__name__}: {e}"
        log.error("job failed", extra={"job": job_id, "trace": traceback.format_exc()[-3000:]})
    with session() as db:
        j = db.get(Job, job_id)
        j.status, j.result, j.error = status, result, error
        j.finished_at = datetime.now(timezone.utc)
        if status == "done":
            j.progress = 1.0
        if pid and error:
            p = db.get(Project, pid)
            if p:
                p.data = {**p.data, "last_error": {"job": job_id, "type": typ, "error": error}}
                if p.state in ("RENDERING", "BUILDING_MASTERS", "UPLOADING_PRIVATE", "GENERATING_OR_IMPORTING_IMAGES", "QUALITY_CHECK"):
                    from app.services import state_machine as sm
                    back = {"RENDERING": "PREVIEW_APPROVED", "QUALITY_CHECK": "PREVIEW_APPROVED", "BUILDING_MASTERS": "IMAGE_APPROVED",
                            "UPLOADING_PRIVATE": "READY_FOR_UPLOAD", "GENERATING_OR_IMPORTING_IMAGES": "CONCEPT_APPROVED"}[p.state]
                    sm.transition(db, p, back if back != "CONCEPT_APPROVED" else "IMAGE_REVIEW", note=f"job {job_id} {status}; restart this stage")
    log.info("job end", extra={"job": job_id, "status": status})
    return status


def main(once=False):
    setup_logging()
    migrate()
    n = recover_stale()
    if n:
        log.info("recovered interrupted jobs", extra={"count": n})
    signal.signal(signal.SIGTERM, lambda *_: globals().__setitem__("_stop", True))
    poll = get_settings().worker_poll_seconds
    while not _stop:
        jid = claim_next()
        if jid:
            run_one(jid)
            if once:
                return
        else:
            if once:
                return
            time.sleep(poll)


if __name__ == "__main__":
    main()
