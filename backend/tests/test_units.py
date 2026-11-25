import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pytest

from app.db import session
from app.models import Job, Keyword, Project
from app.services import budget, settings_store
from app.services import state_machine as sm


# ---------------------------------------------------------------- budget / paid providers

def test_paid_provider_blocked_by_default():
    from app.providers.registry import RunwayProvider
    with session() as db:
        with pytest.raises(budget.PaidProviderBlocked, match="disabled"):
            RunwayProvider().submit(db, {}, project_id=None, request_key="k1", user_approved=True)


def test_budget_enforcement_and_duplicates():
    with session() as db:
        settings_store.put(db, "budget", {"paid_api_enabled": True, "allowed_paid_providers": ["openai"],
                                          "monthly_api_budget_eur": 1.0, "per_project_api_budget_eur": 1.0})
        kw = dict(provider="openai", model="m", project_id="p", user_approved=True)
        with pytest.raises(budget.PaidProviderBlocked, match="approval"):
            budget.reserve(db, **{**kw, "user_approved": False}, estimated_eur=0.1, request_key="a")
        with pytest.raises(budget.PaidProviderBlocked, match="unknown"):
            budget.reserve(db, **kw, estimated_eur=None, request_key="a")
        e = budget.reserve(db, **kw, estimated_eur=0.6, request_key="a")
        with pytest.raises(budget.PaidProviderBlocked, match="duplicate"):
            budget.reserve(db, **kw, estimated_eur=0.1, request_key="a")
        with pytest.raises(budget.PaidProviderBlocked, match="budget"):
            budget.reserve(db, **kw, estimated_eur=0.6, request_key="b")
        budget.release(db, e)
        db.rollback()
        settings_store.put(db, "budget", {"paid_api_enabled": False, "allowed_paid_providers": []})


def test_enabling_paid_requires_explicit_confirmation(client):
    r = client.put("/api/settings/budget", json={"paid_api_enabled": True})
    assert r.status_code == 400


# ---------------------------------------------------------------- state machine

def test_state_machine_gates():
    with session() as db:
        p = Project(id="sm-test", name="x", state="IMAGE_REVIEW", data={})
        db.add(p)
        db.flush()
        with pytest.raises(sm.TransitionError):
            sm.transition(db, p, "IMAGE_APPROVED", actor="system")  # human-only
        sm.transition(db, p, "IMAGE_APPROVED", actor="user")
        sm.approve(db, p, "image", "approved", None, "1")
        sm.approve(db, p, "preview", "approved", None, "h")
        p.state = "PREVIEW_APPROVED"
        sm.invalidate_from(db, p, "preview", "config changed")
        assert sm.valid_approval(db, p, "preview") is None
        assert sm.valid_approval(db, p, "image") is not None
        assert p.state == "IMAGE_APPROVED"


def test_job_recovery_after_crash():
    from app.workers.queue import enqueue, recover_stale
    with session() as db:
        j = enqueue(db, "noop", None)
        j.status, j.attempts, j.heartbeat_at = "running", 1, datetime.now(timezone.utc) - timedelta(minutes=10)
        jid = j.id
    assert recover_stale() >= 1
    with session() as db:
        assert db.get(Job, jid).status == "queued"
        db.get(Job, jid).status = "cancelled"


# ---------------------------------------------------------------- research

def test_scoring_reweights_missing_inputs_and_never_invents():
    from app.research.scoring import score
    k = Keyword(keyword="x", cluster="sleep")
    w = {"demand": .25, "competition": .2, "small_channel": .15, "evergreen": .15, "differentiation": .15, "feasibility": .1}
    r = score(k, w)
    assert set(r["breakdown"]) == {"evergreen"} and "demand" in r["missing"] and r["confidence"] < 0.1
    k.est_monthly_volume, k.volume_kind, k.volume_source = 50_000, "third_party_estimate", "vidiq"
    r2 = score(k, w)
    assert r2["breakdown"]["demand"]["kind"] == "third_party_estimate" and r2["confidence"] > r["confidence"]


def test_keyword_csv_relative_interest(client):
    csv = "Query,Interest\nlibrary ambience,63\n"
    client.post("/api/keywords/import", files={"file": ("t.csv", csv)}, data={"source": "google_trends_youtube", "kind": "relative_interest"})
    k = next(k for k in client.get("/api/keywords").json() if k["keyword"] == "library ambience")
    assert k["trend_interest"] == 63 and k["est_monthly_volume"] is None  # relative interest is never a volume


def test_youtube_research_cache_quota_and_competitors():
    from app.providers.keyword_research.youtube_data_api import YouTubeResearch, units_today
    from app.research import service
    now = datetime.now(timezone.utc)
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.path)
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "v1"}}, {"id": {"videoId": "v2"}}]})
        if req.url.path.endswith("/videos"):
            mk = lambda i, ch, views, days: {"id": i, "snippet": {"channelId": ch, "title": f"t{i}", "publishedAt": (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")},
                                             "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": "PT8H"}}
            return httpx.Response(200, json={"items": [mk("v1", "c1", 500_000, 100), mk("v2", "c2", 10_000, 50)]})
        return httpx.Response(200, json={"items": [
            {"id": "c1", "snippet": {"title": "Small"}, "statistics": {"subscriberCount": "20000", "viewCount": "1", "videoCount": "3"}},
            {"id": "c2", "snippet": {"title": "Hidden"}, "statistics": {"hiddenSubscriberCount": True, "viewCount": "1", "videoCount": "3"}}]})

    with session() as db:
        yt = YouTubeResearch(db, "dummy", daily_limit=1000, transport=httpx.MockTransport(handler))
        ids = yt.search_videos("rain sounds for sleeping")
        yt.search_videos("rain sounds for sleeping")  # cached
        vids, chans = yt.videos(ids), yt.channels(["c1", "c2"])
        assert calls.count("/youtube/v3/search") == 1 and units_today(db) == 102
        service.ingest_api_items(db, "rain sounds for sleeping", "sleep", vids, chans)
        k = db.query(Keyword).filter_by(keyword="rain sounds for sleeping").one()
        service.update_keyword_from_competitors(db, k)
        rows = {r["video_id"]: r for r in service.video_table(db, "rain sounds for sleeping")}
        assert rows["v1"]["views_per_subscriber"] == 25.0 and rows["v1"]["outperformer"] and rows["v1"]["small_channel"]
        assert rows["v2"]["subscribers"] is None  # hidden count respected
        assert rows["v1"]["measured_recent_views_per_day"] is None  # one snapshot: no measured growth claimed
        assert k.small_channel_success == 0.5 and k.opportunity_score is not None


# ---------------------------------------------------------------- audio

def test_audio_determinism_and_chunking():
    from app.media.mixing.mixer import stream
    cfg = {"seed": 3, "layers": [{"id": "r", "type": "rain"}, {"id": "o", "type": "ocean"}, {"id": "t", "type": "rhythm"}]}
    a = np.concatenate(list(stream(cfg, 5)))
    b = np.concatenate(list(stream(cfg, 12)))[: len(a)]
    # identical except the fade-out region of the shorter render
    assert np.allclose(a[:48000 * 1], b[:48000 * 1])
    assert a.shape == (5 * 48000, 2) and np.isfinite(a).all()


def test_mute_solo_and_limiter():
    from app.media.mixing.mixer import safety_limit, stream
    cfg = {"seed": 1, "layers": [{"id": "a", "type": "hum"}, {"id": "b", "type": "wind", "mute": True}]}
    only = np.concatenate(list(stream(cfg, 2)))
    cfg2 = {"seed": 1, "layers": [{"id": "a", "type": "hum", "solo": True}, {"id": "b", "type": "wind"}]}
    assert np.allclose(only, np.concatenate(list(stream(cfg2, 2))))
    x = np.linspace(-3, 3, 1000)[:, None]
    assert np.abs(safety_limit(x, -2)).max() <= 10 ** (-2 / 20) + 1e-6


def test_loop_layer_crossfade(ws):
    from scipy.io import wavfile
    from app.media.mixing.mixer import FileLoopLayer
    p = ws / "tone.wav"
    t = np.arange(48000 * 3) / 48000
    wavfile.write(p, 48000, np.stack([np.sin(2 * np.pi * 220 * t)] * 2, 1).astype(np.float32) * 0.5)
    layer = FileLoopLayer(sr=48000, seed=1, path=str(p), crossfade_s=0.5)
    y = np.concatenate([layer.render(48000) for _ in range(8)])
    assert np.abs(np.diff(y[:, 0])).max() < 0.1  # no clicks at loop points


# ---------------------------------------------------------------- animation, masks, rendering

def test_masks_polygon_invert_feather():
    from app.media.animation.masks import build_mask
    m = build_mask({"polygons": [[[0, 0], [0.5, 0], [0.5, 1], [0, 1]]], "feather": 0.02}, 200, 100)
    assert m[50, 10] > 0.99 and m[50, 190] < 0.01 and 0.1 < m[50, 100] < 0.9
    assert build_mask({"rect": [0, 0, 1, 0.5], "invert": True, "feather": 0}, 10, 10)[9, 5] == 1


def test_every_effect_loops_seamlessly(ws):
    import cv2
    from app.media.animation.effects import EFFECTS
    from app.media.rendering.render import loop_check
    img = ws / "base.png"
    cv2.imwrite(str(img), (np.random.default_rng(1).uniform(0, 255, (90, 160, 3))).astype(np.uint8))
    for t in EFFECTS:
        params = {"kind": "rain", "speed": [300, 600]} if t == "particles" else {}
        r = loop_check(None, img, {"effects": [{"type": t, "params": params}]}, 160, 90, 12, 4, ws)
        assert r["seamless"], (t, r)


def test_render_master_and_long_assembly(ws):
    """Extended rendering check: stream-copied visual loop + streamed audio, duration/sync validated (5 min)."""
    import cv2
    from app.media.rendering import ffmpeg as ff
    from app.media.rendering.render import render_final, render_master
    img = ws / "base2.png"
    cv2.imwrite(str(img), np.full((180, 320, 3), 60, np.uint8))
    master = ws / "m.mp4"
    render_master(img, {"effects": [{"type": "particles", "params": {"kind": "snow", "count": 50}}]}, master,
                  w=320, h=180, fps=24, loop_s=4, workspace=ws)
    out = ws / "long.mp4"
    render_final(master, {"seed": 1, "layers": [{"id": "w", "type": "wind"}]}, 300, out)
    info = ff.probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert abs(float(info["format"]["duration"]) - 300) < 0.5
    assert abs(float(v["duration"]) - float(a["duration"])) < 0.5
    assert int(v["nb_frames"]) in range(300 * 24 - 2, 300 * 24 + 3)  # monotonic, complete timestamps


# ---------------------------------------------------------------- metadata, licensing, security, analytics

def test_metadata_limits_and_medical_claims():
    from app.publishing.metadata import Metadata, fit_tags, validate
    m = Metadata(primary_keyword="k", title_candidates=["a"], title="x" * 101, description="This cures insomnia <b>", tags=[])
    errs = " ".join(validate(m))
    assert "1–100" in errs and "<" in errs and "medical" in errs
    assert sum(len(t) for t in fit_tags([f"tag number {i}" for i in range(100)])) <= 500


def test_license_evaluation():
    from app.licensing.licenses import evaluate
    assert not evaluate({})["ok"]
    assert not evaluate({"name": "CC-BY-NC-4.0", "creator": "x"})["ok"]
    assert not evaluate({"name": "CC-BY-4.0"})["ok"]  # attribution needs creator
    ok = evaluate({"name": "CC-BY-4.0", "creator": "Jane", "title": "Rain", "source_url": "https://freesound.org/s/1"})
    assert ok["ok"] and "Jane" in ok["attribution_text"]
    assert evaluate({"name": "CC0-1.0"})["ok"]


def test_secret_redaction_and_path_traversal(client):
    from app.logging_setup import redact
    assert "abc123secret" not in redact("GET /x?key=abc123secret&q=1")
    for path in ("/api/files/..%2F..%2F..%2F..%2Fetc%2Fpasswd", "/api/files/%2Fetc%2Fpasswd"):
        r = client.get(path)
        assert r.status_code in (403, 404) and "root:" not in r.text, path
    assert client.get("/api/settings").text.find("youtube_api_key") == -1  # credentials never sent to frontend


def test_forecast_handles_zero_costs():
    from app.analytics.business import forecast
    f = forecast({"monthly_operating_cost_eur": 0, "production_cost_per_video_eur": 0, "months": 6, "monetization_month": 3})
    assert f["base"]["break_even_monthly_views"] == 0 and f["base"]["payback_month"] == "no costs to recover"
    assert f["base"]["rows"][0]["revenue_eur"] == 0  # no ad revenue before monetization


def test_studio_csv_import_and_no_mock_analytics(client):
    assert client.get("/api/analytics").json()["ypp"]["tiers"]["full_ads"]["subscribers"]["current"] is None
    csv = "Content,Video title,Views,Watch time (hours),Subscribers\nTotal,,100,20,3\nabc123,Saturn,100,20,3\n"
    r = client.post("/api/analytics/import", files={"file": ("s.csv", csv)}, data={"period_start": "2026-11-01", "period_end": "2026-11-24"})
    assert r.json()["rows"] == 2


def test_hardware_detection_runs():
    from app.hardware.detect import detect
    info = detect(test_encoders=False)
    assert info["cpu_threads"] >= 1 and "assessment" in info and info["assessment"]["procedural_animation"]["level"]
