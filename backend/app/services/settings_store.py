"""Business settings stored in the DB (editable from the dashboard). Never hardcode brand values elsewhere."""
import copy

from sqlalchemy.orm import Session

from app.models import Setting

DEFAULTS: dict[str, dict] = {
    "brand": {
        "brand_name": "Driftbound Ambience",
        "app_name": "Driftbound Studio",
        "channel_display_name": "Driftbound – Sleep & Relaxing Sounds",
        "preferred_handle": "@DriftboundAmbience",
        "handle_verified": False,
        "tagline": "Drift into another world.",
        "language": "en",
        "market": "international",
        "positioning": "Premium immersive environments for sleep, relaxation, focus and quiet moments.",
        "palette": {
            "midnight_blue": "#142139", "deep_navy": "#0C1528", "muted_gold": "#D9C9A0",
            "warm_ivory": "#EEE5D5", "atmospheric_blue": "#91A9B8",
        },
        "typography": {"thumbnail_font": "Pillow default (Aileron, CC0)", "ui_font": "system-ui"},
        "watermark": {"enabled": False, "text": "DRIFTBOUND", "opacity": 0.25},
        "channel_description": (
            "Drift into another world.\n\nDiscover immersive environments and carefully crafted soundscapes for "
            "sleep, relaxation, studying and focus.\n\nFrom peaceful mountain cabins and ancient libraries to "
            "underwater sanctuaries and distant galaxies, Driftbound takes you beyond the noise of everyday life.\n\n"
            "Original worlds. Atmospheric sounds. Hours of peaceful ambience.\n\nFind your escape."
        ),
        "channel_keywords": ["sleep sounds", "ambience", "relaxing sounds", "study ambience", "space ambience"],
        "thumbnail_guidelines": "One clear focal point, cinematic contrast, minimal text (max 3 words), no claims.",
        "playlists": [
            {"name": "Deep Sleep Worlds", "description": "Long, calm environments for falling and staying asleep.", "categories": ["sleep"]},
            {"name": "Focus & Study Ambience", "description": "Steady background worlds for reading, studying and work.", "categories": ["study", "focus"]},
            {"name": "Relaxing Escapes", "description": "Peaceful places to unwind.", "categories": ["relaxation"]},
        ],
    },
    "budget": {
        "paid_api_enabled": False,
        "monthly_api_budget_eur": 0.0,
        "per_project_api_budget_eur": 0.0,
        "paid_fallback_enabled": False,
        "cloud_rendering_enabled": False,
        "allowed_paid_providers": [],
        "electricity_eur_per_kwh": None,
        "render_power_watts": None,
        "existing_subscriptions": [],  # [{"name": ..., "monthly_eur": ..., "allocated_share": 0.0}]
        "hourly_value_of_manual_effort_eur": None,
    },
    "render": {
        "default_duration_hours": 8,
        "width": 1920, "height": 1080, "fps": 30,
        "video_encoder": "auto",  # auto -> first tested working encoder, else libx264
        "crf": 20, "preset": "medium", "video_bitrate_kbps_estimate": 6000,
        "audio_bitrate_kbps": 192, "sample_rate": 48000,
        "loop_seconds": 60,
        "concurrency": 1,
    },
    "audio_profiles": {
        "sleep": {"target_lufs": -20.0, "true_peak_db": -2.0, "lowpass_hz": 9000},
        "focus": {"target_lufs": -18.0, "true_peak_db": -1.5, "lowpass_hz": 14000},
    },
    "providers": {
        "llm": "auto",  # auto -> ollama if reachable else template
        "llm_model": "",
        "image": "procedural",  # procedural | comfyui | import
        "comfyui_workflow": "",
        "youtube_publisher": "mock",  # mock | youtube
        "keyword_research": "manual",  # manual | youtube_data_api
    },
    "research": {"max_results_per_query": 25, "daily_quota_limit": 8000, "cache_hours": 24, "retention_days": 30},
    "publishing": {"default_privacy": "private", "made_for_kids_confirmed": None, "default_category_id": "10"},
    "automation": {"mode": "semi"},  # manual | semi | batch
    "scoring_weights": {
        "demand": 0.25, "competition": 0.20, "small_channel": 0.15,
        "evergreen": 0.15, "differentiation": 0.15, "feasibility": 0.10,
    },
}


def get(db: Session, key: str) -> dict:
    row = db.get(Setting, key)
    base = copy.deepcopy(DEFAULTS.get(key, {}))
    if row:
        base.update(row.value)
    return base


def put(db: Session, key: str, value: dict) -> dict:
    merged = get(db, key)
    merged.update(value)
    row = db.get(Setting, key)
    if row:
        row.value = merged
    else:
        db.add(Setting(key=key, value=merged))
    db.flush()
    return merged


def all_settings(db: Session) -> dict:
    return {k: get(db, k) for k in DEFAULTS}
