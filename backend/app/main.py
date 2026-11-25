"""FastAPI app. Run: `uvicorn app.main:app --host 127.0.0.1 --port 8000` (localhost only by default)."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import api
from app.config.settings import REPO_ROOT
from app.db import migrate, session
from app.logging_setup import setup_logging
from app.services.seed import seed


@asynccontextmanager
async def lifespan(_):
    setup_logging()
    migrate()
    with session() as db:
        seed(db)
    yield


app = FastAPI(title="Driftbound Studio", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"], allow_methods=["*"],
                   allow_headers=["*"])
app.include_router(api)

DIST = REPO_ROOT / "frontend" / "dist"
if DIST.exists():  # serve the built dashboard from the same localhost port
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="static")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            from fastapi import HTTPException
            raise HTTPException(404, "not found")
        f = DIST / path
        return FileResponse(f if path and f.is_file() and f.resolve().is_relative_to(DIST.resolve()) else DIST / "index.html")
