"""Concept schema, seed catalogue (spec 14), template briefs and scoring (spec 13)."""
from pydantic import BaseModel, Field

from app.services.scenes import scene


class ConceptData(BaseModel):
    name: str
    category: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    search_intent: list[str] = Field(default_factory=list)
    research_evidence: list[dict] = Field(default_factory=list)
    environment: str
    audience: str = "Adults seeking peaceful background ambience"
    creative_direction: str = "Photorealistic, cinematic, calm and immersive"
    visual_elements: list[str] = Field(default_factory=list)
    animated_elements: list[str] = Field(default_factory=list)
    audio_layers: list[str] = Field(default_factory=list)
    recommended_production_methods: list[str] = Field(default_factory=list)
    unique_selling_point: str = ""
    duration_hours: float = 8
    estimated_api_cost_eur: float = 0
    title_candidates: list[str] = Field(default_factory=list)
    thumbnail_direction: str = ""
    originality_notes: str = ""
    synthetic_content_disclosure_recommendation: bool = True
    image_prompt: str = ""
    negative_prompt: str = ""
    scene: dict = Field(default_factory=dict)  # {"audio": [...preset keys], "fx": [...]}
    free_production_suitability: str = "medium"


NEG = "text, letters, watermark, logo, signature, people, faces, distorted perspective, blurry, oversaturated, cartoon"

# name, hours, category, environment, audio desc, animation desc, keywords, audio presets, fx presets, suitability, visual elements
SEED = [
    ("Sleeping Near Saturn", 8, "sleep", "A futuristic bedroom overlooking Saturn",
     ["deep spacecraft hum", "ventilation", "soft atmospheric textures"], ["subtle star twinkle", "slow nebula drift", "ambient lighting"],
     ["space ambience", "sleep sounds", "spaceship ambience"], ["space"], ["stars", "space_clouds", "ambient"], "high",
     ["panoramic window", "Saturn with rings", "dim warm bedside light", "soft linen bed"]),
    ("Rainy Mountain Cabin", 8, "sleep", "A warm wooden cabin overlooking a rainy mountain forest",
     ["rain", "fireplace", "gentle wind"], ["window rain", "falling droplets", "fireplace glow"],
     ["rain sounds for sleeping", "cozy cabin ambience"], ["rain_interior", "fireplace"], ["rain", "droplets", "fire_glow"], "medium",
     ["large window", "misty pine forest", "stone fireplace", "wooden beams"]),
    ("Underwater Sanctuary", 8, "sleep", "A peaceful underwater bedroom with panoramic ocean views",
     ["deep ocean textures", "subtle water movement", "environmental hum"], ["underwater light patterns", "floating particles"],
     ["underwater ambience", "ocean sleep sounds"], ["underwater"], ["caustics", "particles_uw", "bubbles"], "high",
     ["glass dome", "blue light shafts", "coral silhouettes", "minimal bed"]),
    ("Midnight Alpine Express", 4, "sleep", "A luxury sleeper train traveling through snowy mountains at night",
     ["rhythmic railway sounds", "gentle carriage ambience"], ["snow passing the window", "subtle reflections"],
     ["train sounds for sleeping", "night train ambience"], ["train"], ["snow", "ambient"], "medium",
     ["sleeper cabin window", "snowy peaks", "warm reading lamp"]),
    ("Medieval Castle Library", 3, "study", "A candlelit castle library during a distant storm",
     ["fireplace", "soft rain", "room ambience"], ["candle flicker", "fireplace glow", "window rain"],
     ["library ambience", "fireplace ambience", "medieval ambience"], ["rain_interior", "fireplace"], ["candles", "fire_glow", "rain"], "medium",
     ["tall bookshelves", "arched window", "candelabras", "reading desk"]),
    ("Snowed-In Forest Retreat", 8, "sleep", "A secluded cabin surrounded by snowfall",
     ["winter wind", "fireplace", "indoor ambience"], ["snow particles", "subtle lighting"],
     ["snowstorm ambience", "cozy cabin ambience"], ["wind", "fireplace"], ["snow", "fire_glow"], "medium",
     ["frosted window", "snowy firs", "armchair", "fireplace"]),
    ("Japanese Garden at Dawn", 2, "relaxation", "A tranquil traditional garden at dawn",
     ["flowing water", "gentle birdsong (licensed recording)", "wind"], ["water movement", "subtle vegetation movement"],
     ["nature sounds", "relaxing sounds", "water sounds"], ["water", "wind"], ["water_shimmer", "sway", "fog"], "low",
     ["stone lantern", "koi pond", "maple trees", "morning mist"]),
    ("Lighthouse During a Storm", 3, "relaxation", "A coastal lighthouse during nighttime rain",
     ["distant waves", "rain", "wind"], ["rainfall", "clouds", "distant ocean movement"],
     ["rainy night ambience", "ocean sounds for sleeping"], ["storm", "ocean"], ["rain", "clouds", "water_shimmer"], "medium",
     ["lighthouse beam", "cliffs", "stormy sea", "dark clouds"]),
    ("Desert Observatory", 8, "sleep", "A remote observatory overlooking a star-filled desert",
     ["quiet nighttime wind", "subtle room ambience"], ["star movement", "subtle atmospheric lighting"],
     ["space ambience", "sleep ambience"], ["wind"], ["stars", "ambient"], "high",
     ["telescope dome", "dunes", "milky way", "warm interior light"]),
    ("Rainy Tokyo Apartment", 3, "focus", "An atmospheric apartment overlooking a rainy city",
     ["rain on windows", "distant urban ambience"], ["rainfall", "reflections", "city lights"],
     ["rain sounds", "study ambience", "background sounds for work"], ["rain_interior"], ["droplets", "rain", "ambient"], "medium",
     ["floor-to-ceiling window", "neon bokeh", "desk lamp", "plants"]),
    ("Hidden Waterfall Grotto", 2, "relaxation", "A secluded natural cavern with a waterfall",
     ["flowing water", "cavern acoustics"], ["water effects", "moving reflections"],
     ["water sounds", "nature sounds"], ["water"], ["water_shimmer", "caustics", "fog"], "low",
     ["waterfall", "moss", "light shaft", "still pool"]),
    ("Arctic Research Station", 8, "sleep", "A warm bedroom overlooking an Arctic landscape",
     ["gentle mechanical hum", "distant winter wind"], ["snowfall", "stars", "environmental lighting"],
     ["sleep sounds", "snowstorm ambience"], ["space", "wind"], ["stars", "snow", "ambient"], "high",
     ["wide window", "ice plains", "aurora hint", "warm bunk"]),
    ("Cozy Houseboat at Night", 4, "sleep", "A warmly lit houseboat on peaceful water",
     ["gentle water against the hull", "room ambience"], ["water ripples", "moving reflections"],
     ["water sounds", "sleep sounds"], ["ocean"], ["water_shimmer", "ambient"], "medium",
     ["porthole window", "canal reflections", "lanterns"]),
    ("Ancient Forest Temple", 3, "relaxation", "A secluded temple in a lush ancient forest",
     ["forest ambience", "flowing streams", "gentle wind"], ["floating particles", "mist", "subtle vegetation movement"],
     ["nature sounds", "fantasy ambience"], ["water", "wind"], ["fog", "sway", "particles_uw"], "low",
     ["moss-covered stone", "giant trees", "light rays"]),
    ("Cloudtop Bedroom", 8, "sleep", "A dreamlike bedroom overlooking an endless cloudscape",
     ["soft wind", "atmospheric textures"], ["slowly moving clouds", "subtle lighting"],
     ["sleep sounds", "relaxing ambience"], ["wind"], ["clouds", "ambient"], "high",
     ["open balcony", "sea of clouds", "golden hour light", "white curtains"]),
]


def template_concept(row) -> ConceptData:
    name, hours, cat, env, audio, anim, kws, a_keys, fx_keys, suit, visuals = row
    pk = kws[0]
    h = f"{int(hours)} Hours"
    use = {"sleep": "Deep Sleep", "study": "Reading & Studying", "focus": "Focus & Work", "relaxation": "Relaxation"}[cat]
    prompt = (f"{env}, {', '.join(visuals)}, cinematic wide shot, 16:9 composition, fixed camera, atmospheric lighting, "
              f"peaceful mood, depth, high detail, photorealistic, color palette deep navy, muted gold and warm ivory")
    return ConceptData(
        name=name, category=cat, primary_keyword=pk, secondary_keywords=kws[1:],
        search_intent=[f"{cat} background audio", "long uninterrupted ambience"],
        research_evidence=[{"kind": "hypothesis", "note": "Seed concept from the initial catalogue; not yet validated by research."}],
        environment=env, visual_elements=visuals, animated_elements=anim, audio_layers=audio,
        recommended_production_methods=["procedural animation", "local audio synthesis"] +
        (["licensed recording for " + a for a in audio if "licensed" in a or "fireplace" in a or "birdsong" in a]) +
        (["procedural painter or ComfyUI image"] if suit == "high" else ["ComfyUI image or manual import"]),
        unique_selling_point=f"An original, scene-specific soundscape for '{env.lower()}', mixed for {cat}.",
        duration_hours=hours, title_candidates=[
            f"{pk.title()} | {name} – {h}", f"{name} | {pk.title()} for {use} – {h}",
            f"{use} Ambience: {name} ({h})", f"{name} – {h} of {audio[0].capitalize()}",
            f"{pk.title()} – {name} | {h}"],
        thumbnail_direction=f"One focal element ({visuals[0]}), dark surround, warm accent light, no more than 3 words.",
        originality_notes="Original environment and synthesized soundscape; competitor research used only for demand signals.",
        image_prompt=prompt, negative_prompt=NEG, scene={"audio": a_keys, "fx": fx_keys},
        free_production_suitability=suit,
    )


def default_project_config(concept: ConceptData) -> dict:
    s = scene(concept.scene.get("audio", ["wind"]), concept.scene.get("fx", ["ambient"]))
    profile = "sleep" if concept.category in ("sleep", "relaxation") else "focus"
    s["audio"]["profile"] = profile
    return s


CRITERIA = ["audience_relevance", "originality", "visual_appeal", "sound_design", "search_opportunity", "evergreen",
            "feasibility", "brand_alignment", "differentiation"]


def heuristic_scores(c: ConceptData, keyword_score: float | None, existing_names: list[str]) -> dict:
    """Transparent heuristic scores (0-1). Labeled heuristic; search_opportunity comes only from research data."""
    suit = {"high": 0.9, "medium": 0.65, "low": 0.4}[c.free_production_suitability]
    similar = [n for n in existing_names if n != c.name and len(set(n.lower().split()) & set(c.name.lower().split())) >= 2]
    s = {
        "audience_relevance": 0.8 if c.category in ("sleep", "study", "focus", "relaxation") else 0.5,
        "originality": 0.8 if c.environment and not similar else 0.5,
        "visual_appeal": 0.75 if len(c.visual_elements) >= 3 else 0.55,
        "sound_design": min(1.0, 0.4 + 0.15 * len(c.audio_layers)),
        "search_opportunity": keyword_score,
        "evergreen": 0.85 if c.category in ("sleep", "relaxation") else 0.7,
        "feasibility": suit,
        "brand_alignment": 0.85,
        "differentiation": 0.4 if similar else 0.75,
    }
    vals = [v for v in s.values() if v is not None]
    s["overall"] = round(sum(vals) / len(vals), 3)
    s["kind"] = "heuristic"
    s["missing"] = [k for k, v in s.items() if v is None]
    s["similar_to"] = similar
    return s
