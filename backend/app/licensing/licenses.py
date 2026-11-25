"""License evaluation for imported/generated assets (spec 21). Conservative: unknown = blocked."""

KNOWN = {
    "CC0-1.0": {"commercial": True, "attribution": False},
    "public-domain": {"commercial": True, "attribution": False},
    "CC-BY-4.0": {"commercial": True, "attribution": True},
    "CC-BY-3.0": {"commercial": True, "attribution": True},
    "CC-BY-NC-4.0": {"commercial": False, "attribution": True},
    "CC-BY-NC-3.0": {"commercial": False, "attribution": True},
    "CC-BY-SA-4.0": {"commercial": True, "attribution": True, "share_alike": True},
    "pixabay-content-license": {"commercial": True, "attribution": False,
                                "note": "Check the current Pixabay Content License; some uses (e.g. standalone redistribution) are restricted"},
    "user-owned": {"commercial": True, "attribution": False},
    "generated-local": {"commercial": True, "attribution": False},
}


def evaluate(lic: dict) -> dict:
    """lic: {name, source, source_url, creator, commercial_use(bool|None), attribution_required, restrictions, evidence}"""
    issues = []
    name = (lic or {}).get("name")
    k = KNOWN.get(name or "", {})
    commercial = lic.get("commercial_use") if lic and lic.get("commercial_use") is not None else k.get("commercial")
    if not name:
        issues.append("No license recorded")
    if commercial is None:
        issues.append("Commercial use not established")
    elif commercial is False:
        issues.append("Non-commercial license: cannot be used on a monetized channel")
    attribution = lic.get("attribution_required", k.get("attribution", False)) if lic else False
    if attribution and not lic.get("creator"):
        issues.append("Attribution required but creator is missing")
    if k.get("share_alike"):
        issues.append("Share-alike license: check compatibility before publishing (flag)")
    if name and name not in KNOWN and not lic.get("evidence"):
        issues.append("Custom license without stored evidence (license text or URL)")
    blocking = [i for i in issues if not i.endswith("(flag)")]
    return {"ok": not blocking, "issues": issues, "commercial": commercial, "attribution": attribution,
            "attribution_text": f"{lic.get('title', 'Sound')} by {lic.get('creator')} ({name}) {lic.get('source_url', '')}".strip()
            if attribution and lic.get("creator") else None}


def evaluate_asset(asset) -> dict:
    if asset.provider in ("procedural", "synth", "driftbound"):
        return {"ok": True, "issues": [], "commercial": True, "attribution": False, "attribution_text": None}
    return evaluate(asset.license or {})
