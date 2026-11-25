"""SEO metadata generation (templates or local LLM) + YouTube limit enforcement (spec 26)."""
import re

from pydantic import BaseModel, Field

TITLE_MAX = 100  # characters
DESC_MAX_BYTES = 5000
TAGS_MAX_CHARS = 500  # combined; YouTube counts quoted multi-word tags with their quotes
FORBIDDEN = re.compile(r"[<>]")
MEDICAL = re.compile(r"\b(cure[sd]?|treat(s|ment)?|heal(s|ing)?|insomnia relief|anxiety relief|guaranteed)\b", re.I)


class Metadata(BaseModel):
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    title_candidates: list[str]
    title: str
    description: str
    tags: list[str]
    playlist: str | None = None
    category_id: str = "10"  # Music; verify the best fit (e.g. 22 People & Blogs) for your channel
    language: str = "en"
    thumbnail_recommendation: str = ""
    synthetic_disclosure: dict = Field(default_factory=dict)


def tags_length(tags: list[str]) -> int:
    return sum(len(t) + (2 if " " in t else 0) for t in tags) + max(0, len(tags) - 1)


def validate(m: Metadata) -> list[str]:
    errs = []
    if not m.title or len(m.title) > TITLE_MAX:
        errs.append(f"Title must be 1–{TITLE_MAX} characters (is {len(m.title)}).")
    if len(m.description.encode()) > DESC_MAX_BYTES:
        errs.append(f"Description exceeds {DESC_MAX_BYTES} bytes.")
    if FORBIDDEN.search(m.title) or FORBIDDEN.search(m.description):
        errs.append("Title/description may not contain < or >.")
    if tags_length(m.tags) > TAGS_MAX_CHARS:
        errs.append(f"Tags exceed {TAGS_MAX_CHARS} characters combined.")
    for field in (m.title, m.description):
        if MEDICAL.search(field):
            errs.append(f"Possible medical claim: '{MEDICAL.search(field).group(0)}'. Remove health promises.")
    return errs


def fit_tags(tags: list[str]) -> list[str]:
    out, seen = [], set()
    for t in tags:
        t = FORBIDDEN.sub("", t).strip()[:60]
        if t and t.lower() not in seen and tags_length(out + [t]) <= TAGS_MAX_CHARS:
            out.append(t)
            seen.add(t.lower())
    return out


def hours_label(h: float) -> str:
    if h < 1:
        m = max(1, round(h * 60))
        return f"{m} Minute{'s' if m != 1 else ''}"
    return f"{int(h)} Hours" if float(h).is_integer() else f"{h:g} Hours"


def template_metadata(concept: dict, duration_h: float, brand: dict, attributions: list[str], disclosure: dict) -> Metadata:
    pk, name = concept["primary_keyword"], concept["name"]
    hl = hours_label(duration_h)
    cands = [t.replace(hours_label(concept.get("duration_hours", duration_h)), hl) for t in concept.get("title_candidates", [])][:5]
    while len(cands) < 5:
        cands.append(f"{pk.title()} | {name} – {hl}"[:TITLE_MAX])
    use = {"sleep": "sleeping, resting and winding down", "study": "reading, studying and focus",
           "focus": "focus, work and study", "relaxation": "relaxing and unwinding"}.get(concept.get("category"), "relaxing")
    sounds = ", ".join(a.replace(" (licensed recording)", "") for a in concept.get("audio_layers", []))
    desc = [
        f"{concept['environment']}. {hl} of {sounds} for {use}.",
        "",
        f"Sounds in this video: {sounds}.",
        f"Visuals: {', '.join(concept.get('animated_elements', []))}.",
        "Steady levels without sudden loud sounds, so it works well as long background ambience.",
        "",
        brand.get("tagline", ""),
    ]
    if attributions:
        desc += ["", "Sound credits:"] + [f"- {a}" for a in attributions]
    if disclosure.get("recommend"):
        desc += ["", "The scene artwork and sounds were created with procedural and AI-assisted tools and edited by hand."]
    tags = fit_tags([pk, *concept.get("secondary_keywords", []), name.lower(), hours_label(duration_h).lower(),
                     concept.get("category", ""), "ambience", "ambient sounds", "relaxing sounds", "sleep sounds"])
    playlist = next((p["name"] for p in brand.get("playlists", []) if concept.get("category") in p.get("categories", [])), None)
    return Metadata(primary_keyword=pk, secondary_keywords=concept.get("secondary_keywords", []), title_candidates=cands,
                    title=cands[0][:TITLE_MAX], description="\n".join(desc)[:DESC_MAX_BYTES], tags=tags, playlist=playlist,
                    thumbnail_recommendation=concept.get("thumbnail_direction", ""), synthetic_disclosure=disclosure)


def disclosure_recommendation(assets: list) -> dict:
    """Recommendation only; the user confirms. YouTube asks creators to disclose realistic altered/synthetic content
    (status.containsSyntheticMedia). Clearly fantastical scenes may not require it; verify current policy."""
    ai = [a for a in assets if (a.provider or "") in ("comfyui", "import_ai", "openai", "runway")]
    realistic = any((a.meta or {}).get("realistic") for a in ai)
    return {"recommend": bool(ai), "contains_synthetic_media_flag": realistic,
            "reason": ("AI-generated imagery present" if ai else "Procedural/original assets only") +
                      ("; scene looks realistic, so the altered/synthetic content flag is recommended" if realistic else ""),
            "requires_user_confirmation": True}
