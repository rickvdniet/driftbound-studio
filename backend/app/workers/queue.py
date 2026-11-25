"""Persistent DB-backed job queue (SQLite). The worker process claims jobs atomically."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import session
from app.models import Job

STALE_AFTER = timedelta(minutes=2)


class Cancelled(Exception):
    pass


def enqueue(db: Session, type_: str, project_id: str | None = None, payload: dict | None = None, max_attempts=2) -> Job:
    j = Job(type=type_, project_id=project_id, payload=payload or {}, max_attempts=max_attempts)
    db.add(j)
    db.flush()
    return j


def claim_next() -> int | None:
    with session() as db:
        for j in db.scalars(select(Job.id).where(Job.status == "queued").order_by(Job.id).limit(5)):
            n = datetime.now(timezone.utc)
            res = db.execute(update(Job).where(Job.id == j, Job.status == "queued").values(
                status="running", started_at=n, heartbeat_at=n, attempts=Job.attempts + 1))
            if res.rowcount == 1:
                return j
    return None


def recover_stale() -> int:
    """After a crash/restart: running jobs without heartbeat are requeued (or failed if out of attempts)."""
    n = 0
    cutoff = datetime.now(timezone.utc) - STALE_AFTER
    with session() as db:
        for j in db.scalars(select(Job).where(Job.status == "running")):
            hb = j.heartbeat_at.replace(tzinfo=timezone.utc) if j.heartbeat_at and j.heartbeat_at.tzinfo is None else j.heartbeat_at
            if hb is None or hb < cutoff:
                if j.attempts < j.max_attempts:
                    j.status, j.message = "queued", "Recovered after interruption; requeued"
                else:
                    j.status, j.error = "failed", "Interrupted and out of attempts"
                n += 1
    return n


class JobContext:
    """Passed to task handlers: progress reporting with cancellation checks and heartbeats."""

    def __init__(self, job_id: int):
        self.job_id = job_id

    def progress(self, frac: float, message: str | None = None):
        with session() as db:
            j = db.get(Job, self.job_id)
            j.progress = max(0.0, min(1.0, frac))
            if message:
                j.message = message
            j.heartbeat_at = datetime.now(timezone.utc)
            if j.cancel_requested:
                raise Cancelled()
