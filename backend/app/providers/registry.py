"""Provider catalogue shown in the dashboard: local vs external, paid flag, licensing notes, status.

Paid providers are interface definitions only (disabled, not implemented). They can never be invoked
without budget.reserve() succeeding, which requires: paid usage enabled, provider allow-listed,
per-job approval, known price, and remaining monthly + per-project budget.
"""
from app.services import budget

PROVIDERS = [
    # kind, name, local, paid, status, notes
    ("llm", "template", True, False, "implemented", "Deterministic templates; always available"),
    ("llm", "ollama", True, False, "implemented", "Local models via Ollama structured outputs; check each model's license"),
    ("llm", "openai", False, True, "interface_only", "Optional paid API. Not implemented; disabled"),
    ("image", "procedural", True, False, "implemented", "CPU scene painter; space skies only"),
    ("image", "import", True, False, "implemented", "Your own or licensed images, incl. images made in existing subscriptions"),
    ("image", "comfyui", True, False, "implemented_unverified", "Local ComfyUI API (/prompt, /history, /view); needs your workflow JSON"),
    ("video", "procedural", True, False, "implemented", "Default animation engine"),
    ("video", "comfyui_i2v", True, False, "planned", "Local image-to-video (e.g. Wan) via ComfyUI; GPU ≥16 GB"),
    ("video", "runway", False, True, "interface_only", "Optional paid API. Not implemented; disabled"),
    ("audio", "synth", True, False, "implemented", "Procedural sound synthesis"),
    ("audio", "licensed_import", True, False, "implemented", "Licensed recordings with provenance"),
    ("audio", "elevenlabs", False, True, "interface_only", "Optional paid API. Not implemented; disabled"),
    ("youtube", "mock", True, False, "implemented", "Offline publisher for tests and dry runs"),
    ("youtube", "youtube", False, False, "implemented_unverified", "Official API, free quota; needs OAuth"),
    ("keyword_research", "manual_csv", True, False, "implemented", "vidIQ / TubeBuddy / Google Trends / Studio CSV imports"),
    ("keyword_research", "youtube_data_api", False, False, "implemented", "Public search/videos/channels data, free quota"),
]


def catalogue():
    return [dict(kind=k, name=n, local=l, paid=p, status=s, notes=no) for k, n, l, p, s, no in PROVIDERS]


class PaidProvider:
    """Base for optional paid providers. submit() always goes through the budget guard first."""
    name = "paid"

    def estimate_eur(self, request: dict) -> float | None:
        return None  # unknown until pricing is verified and entered

    def submit(self, db, request: dict, *, project_id: str | None, request_key: str, user_approved: bool):
        entry = budget.reserve(db, provider=self.name, model=request.get("model"), estimated_eur=self.estimate_eur(request),
                               project_id=project_id, request_key=request_key, user_approved=user_approved)
        budget.release(db, entry)
        raise NotImplementedError(f"{self.name} integration is not implemented (interface only)")


class OpenAIProvider(PaidProvider):
    name = "openai"


class RunwayProvider(PaidProvider):
    name = "runway"


class ElevenLabsProvider(PaidProvider):
    name = "elevenlabs"
