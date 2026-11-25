"""Idempotent first-run seed: keyword clusters + the 15 concept drafts (spec 10 + 14)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Concept
from app.research.service import rescore_all, seed_keywords
from app.services.concepts import SEED, heuristic_scores, template_concept


def seed(db: Session):
    seed_keywords(db)
    rescore_all(db)
    if db.scalar(select(func.count(Concept.id))) == 0:
        names = [r[0] for r in SEED]
        for row in SEED:
            c = template_concept(row)
            db.add(Concept(name=c.name, mode="seed", status="draft", data=c.model_dump(), generated_by="template",
                           scores=heuristic_scores(c, None, names)))
    db.flush()
