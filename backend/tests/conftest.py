import os
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="driftbound_test_")
os.environ["DRIFTBOUND_WORKSPACE"] = _TMP
os.environ["DRIFTBOUND_YOUTUBE_API_KEY"] = ""
os.environ["DRIFTBOUND_OLLAMA_URL"] = "http://127.0.0.1:9"  # unreachable: forces template fallback

from app.config.settings import get_settings  # noqa: E402
from app.db import migrate, session  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    get_settings.cache_clear()
    migrate()
    from app.services.seed import seed
    with session() as db:
        seed(db)
    yield


@pytest.fixture
def ws() -> Path:
    return get_settings().workspace


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
