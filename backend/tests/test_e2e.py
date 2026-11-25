"""Zero-API-cost end-to-end test (spec 40): concept → image → animation → audio → preview → approval →
60 s render → QA → thumbnails → metadata → export → mocked private upload, with €0 paid spend."""
import io

from sqlalchemy import select

from app.db import session
from app.models import CostEntry, Job
from app.workers.queue import claim_next
from app.workers.worker import run_one


def work(client, expect="done"):
    jid = claim_next()
    assert jid, "no job queued"
    status = run_one(jid)
    if status != expect:
        with session() as db:
            raise AssertionError(db.get(Job, jid).error)


def test_zero_cost_workflow(client, ws):
    # 1-2. keyword research import (mock data) + scoring
    csv = "Keyword,Search Volume\nspace sleep sounds,12000\nspaceship ambience,4.4K\n"
    r = client.post("/api/keywords/import", files={"file": ("vidiq.csv", csv)}, data={"source": "vidiq_mock", "kind": "third_party_estimate"})
    assert r.status_code == 200, r.text
    kws = {k["keyword"]: k for k in client.get("/api/keywords").json()}
    assert kws["spaceship ambience"]["est_monthly_volume"] == 4400
    assert kws["spaceship ambience"]["opportunity_score"] is not None

    # 3. concept via template (no LLM reachable) and approval
    c = client.post("/api/concepts/generate", json={"mode": "seo", "keyword_id": kws["space sleep sounds"]["id"]}).json()
    assert c["generated_by"] == "template" and c["data"]["estimated_api_cost_eur"] == 0
    saturn = next(x for x in client.get("/api/concepts").json() if x["name"] == "Sleeping Near Saturn")
    client.post(f"/api/concepts/{saturn['id']}/status", json={"status": "approved"})
    p = client.post(f"/api/concepts/{saturn['id']}/to-project").json()
    pid = p["id"]
    assert p["state"] == "CONCEPT_APPROVED"
    # small test render settings (same pipeline as 1080p)
    client.put(f"/api/projects/{pid}/config", json={"render": {"width": 640, "height": 360, "loop_seconds": 8, "fps": 24,
                                                               "duration_hours": 60 / 3600}})

    # 4. local image (procedural provider) + visual approval gate
    assert client.post(f"/api/projects/{pid}/preview", json={}).status_code == 400  # no image approved yet
    client.post(f"/api/projects/{pid}/images/generate", json={"provider": "procedural", "count": 2})
    work(client)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["state"] == "IMAGE_REVIEW"
    img = next(a for a in proj["assets"] if a["kind"] == "image")
    client.post(f"/api/projects/{pid}/images/{img['id']}/approve")
    proj = client.get(f"/api/projects/{pid}").json()
    assert "sky" in proj["data"]["animation"]["masks"]  # suggested region masks adopted

    # 5-8. procedural visual master + synthesized multi-layer audio + preview
    assert client.post(f"/api/projects/{pid}/render", json={}).status_code == 400  # no preview approval yet
    client.post(f"/api/projects/{pid}/preview", json={"seconds": 20})
    work(client)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["state"] == "PREVIEW_READY", proj["data"].get("last_error")
    assert proj["data"]["loop_check"]["seamless"]
    assert len([a for a in proj["assets"] if a["kind"] == "audio_layer"]) >= 3

    # 9. approve preview; 10. render 60 s
    assert client.post(f"/api/projects/{pid}/preview/approve").status_code == 200
    client.post(f"/api/projects/{pid}/render", json={"duration_s": 60})
    work(client)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["state"] == "FINAL_REVIEW", proj["data"].get("last_error")

    # 11. QA, 12. thumbnails, 13. metadata
    tech = proj["data"]["qa_technical"]
    assert not tech["errors"], tech["errors"]
    assert any(c["check"].startswith("Duration matches") for c in tech["passed"])
    thumbs = [a for a in proj["assets"] if a["kind"] == "thumbnail"]
    assert len(thumbs) == 3 and all(t["width"] == 1280 for t in thumbs)
    meta = proj["data"]["metadata"]
    assert len(meta["title_candidates"]) == 5 and len(meta["title"]) <= 100 and not proj["data"]["metadata_errors"]
    assert not proj["data"]["qa_creative"]["errors"], proj["data"]["qa_creative"]["errors"]

    # approval, export package, mocked private upload
    assert client.post(f"/api/projects/{pid}/approve-final").status_code == 200
    r = client.post(f"/api/projects/{pid}/export")
    assert r.status_code == 200
    exp = ws / r.json()["export_dir"]
    assert (exp / "CHECKLIST.md").exists() and (exp / "manifest.json").exists() and (exp / "thumbnail.jpg").exists()
    client.post(f"/api/projects/{pid}/upload")
    work(client, expect="failed")  # audience ('made for kids') not confirmed yet → blocked
    client.put("/api/settings/publishing", json={"made_for_kids_confirmed": False})
    client.post(f"/api/projects/{pid}/upload")
    work(client)
    proj = client.get(f"/api/projects/{pid}").json()
    assert proj["state"] == "UPLOADED_PRIVATE" and proj["uploads"][0]["privacy"] == "private"
    # duplicate upload protection
    with session() as db:
        from app.models import Project
        db.get(Project, pid).state = "READY_FOR_UPLOAD"
    client.post(f"/api/projects/{pid}/upload")
    work(client, expect="failed")

    # 15. zero paid API expenditure
    with session() as db:
        api = db.scalars(select(CostEntry).where(CostEntry.category == "api")).all()
    assert api == []
    assert client.get("/api/costs").json()["api_total_eur"] == 0
