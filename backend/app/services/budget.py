"""Budget guard: the only path through which any paid provider may be called.

Rules (spec 2 + 30): paid usage disabled by default, budgets €0, no automatic paid fallback,
reservation before submission, unknown pricing requires explicit approval, duplicate protection.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CostEntry
from app.services import settings_store


class PaidProviderBlocked(Exception):
    pass


def _month_start():
    n = datetime.now(timezone.utc)
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def api_spend(db: Session, project_id: str | None = None, statuses=("reserved", "committed")) -> float:
    q = select(func.coalesce(func.sum(func.coalesce(CostEntry.actual_eur, CostEntry.estimated_eur)), 0.0)).where(
        CostEntry.category == "api", CostEntry.status.in_(statuses), CostEntry.at >= _month_start()
    )
    if project_id:
        q = q.where(CostEntry.project_id == project_id)
    return float(db.scalar(q) or 0.0)


def reserve(db: Session, *, provider: str, model: str | None, estimated_eur: float | None, project_id: str | None,
            request_key: str, user_approved: bool) -> CostEntry:
    """Reserve spend for one paid request. Raises PaidProviderBlocked when any rule fails."""
    b = settings_store.get(db, "budget")
    if not b["paid_api_enabled"]:
        raise PaidProviderBlocked("Paid API usage is disabled (Settings → Budget).")
    if provider not in b["allowed_paid_providers"]:
        raise PaidProviderBlocked(f"Provider '{provider}' is not in the allowed paid providers list.")
    if not user_approved:
        raise PaidProviderBlocked("Paid requests require explicit approval for each job.")
    if estimated_eur is None:
        raise PaidProviderBlocked("Pricing is unknown; verify current pricing and enter an estimate first.")
    dup = db.scalar(select(CostEntry).where(CostEntry.request_id == request_key, CostEntry.status != "released"))
    if dup:
        raise PaidProviderBlocked(f"A paid request with key {request_key} already exists (duplicate protection).")
    if api_spend(db) + estimated_eur > b["monthly_api_budget_eur"]:
        raise PaidProviderBlocked("Monthly API budget would be exceeded.")
    if project_id and api_spend(db, project_id) + estimated_eur > b["per_project_api_budget_eur"]:
        raise PaidProviderBlocked("Per-project API budget would be exceeded.")
    entry = CostEntry(category="api", provider=provider, model=model, request_id=request_key,
                      estimated_eur=estimated_eur, status="reserved", project_id=project_id)
    db.add(entry)
    db.flush()
    return entry


def commit(db: Session, entry: CostEntry, actual_eur: float | None):
    entry.status = "committed"
    if actual_eur is not None:
        entry.actual_eur, entry.is_estimate = actual_eur, False


def release(db: Session, entry: CostEntry):
    entry.status = "released"


def record_local_render(db: Session, project_id: str, seconds: float, note: str):
    """Estimated electricity cost of local processing (only if the user configured assumptions)."""
    b = settings_store.get(db, "budget")
    kwh_price, watts = b.get("electricity_eur_per_kwh"), b.get("render_power_watts")
    kwh = (watts or 0) * seconds / 3600 / 1000
    db.add(CostEntry(category="electricity", provider="local", units=round(seconds, 1), project_id=project_id,
                     estimated_eur=round(kwh * kwh_price, 4) if (kwh_price and watts) else 0.0,
                     note=f"{note}; render seconds={seconds:.0f}" + ("" if (kwh_price and watts) else "; no electricity assumptions configured")))
