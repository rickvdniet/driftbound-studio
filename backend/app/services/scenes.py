"""Scene presets: default soundscape layers and animation effects per environment type.

Masks are referenced by name; each project defines its own named masks (drawn in the dashboard or
suggested by the image provider). An effect whose mask name is undefined falls back to the full frame
and is flagged in the UI.
"""
import copy
import zlib

L = lambda id, type, gain_db, **kw: {"id": id, "type": type, "gain_db": gain_db, "seed": zlib.crc32(id.encode()) % 997, **kw}

AUDIO = {
    "space": [L("hum", "hum", -14, params={"f0": 48, "drift": 0.003}, lowpass_hz=900),
              L("ventilation", "ventilation", -22, params={"low": 200, "high": 1800}),
              L("drone", "drone", -18, params={"f0": 55}),
              L("air", "noise", -30, params={"color": "brown", "lowpass": 600})],
    "rain_interior": [L("rain", "rain", -12, params={"drops_per_second": 140}),
                      L("wind", "wind", -24, params={"low": 120, "high": 600}),
                      L("room", "noise", -34, params={"color": "brown", "lowpass": 300})],
    "fireplace": [L("fire", "fire", -16)],
    "underwater": [L("deep", "underwater", -12), L("drone", "drone", -24, params={"f0": 41}),
                   L("hum", "hum", -28, params={"f0": 60}, lowpass_hz=500)],
    "train": [L("rails", "rhythm", -14, params={"period_s": 1.9}), L("carriage", "hum", -24, params={"f0": 70}, lowpass_hz=700),
              L("air", "ventilation", -28)],
    "ocean": [L("ocean", "ocean", -12), L("wind", "wind", -28)],
    "wind": [L("wind", "wind", -14), L("air", "noise", -32, params={"color": "brown", "lowpass": 400})],
    "storm": [L("rain", "rain", -12, params={"drops_per_second": 220}), L("wind", "wind", -20),
              L("thunder", "thunder", -16, params={"per_minute": 0.4})],
    "water": [L("stream", "noise", -16, params={"color": "pink", "highpass": 300, "lowpass": 7000}),
              L("babble", "rain", -22, params={"drops_per_second": 300, "drop_band": [600, 2500], "hiss": 0.2})],
}

FX = {
    "stars": {"type": "stars", "mask": "sky", "params": {"count": 400, "twinkle": 0.35}},
    "space_clouds": {"type": "fog", "mask": "sky", "params": {"kind": "clouds", "density": 0.12, "speed": 4, "color": "#5A6FA8"}},
    "rain": {"type": "particles", "mask": "window", "params": {"kind": "rain", "count": 700, "speed": [500, 1000], "size": [0.6, 1.4], "opacity": 0.35}},
    "droplets": {"type": "window_droplets", "mask": "window", "params": {"count": 260, "sliders": 10}},
    "snow": {"type": "particles", "mask": "window", "params": {"kind": "snow", "count": 500, "speed": [15, 70], "size": [1, 4], "sway": 8}},
    "fire_glow": {"type": "glow", "mask": "fire", "params": {"kind": "fire", "amount": 0.18}},
    "candles": {"type": "glow", "mask": "candles", "params": {"kind": "candle", "amount": 0.12, "radius": 0.03}},
    "embers": {"type": "particles", "mask": "fire", "params": {"kind": "embers", "count": 40, "speed": [20, 60], "size": [0.8, 2], "color": "#FFB060"}},
    "fog": {"type": "fog", "mask": None, "params": {"density": 0.18, "speed": 6}},
    "caustics": {"type": "caustics", "mask": "water", "params": {"strength": 0.12}},
    "particles_uw": {"type": "particles", "mask": "water", "params": {"kind": "dust", "count": 150, "speed": [3, 10], "direction": "up", "size": [0.6, 2], "opacity": 0.3, "sway": 12}},
    "bubbles": {"type": "particles", "mask": "water", "params": {"kind": "bubbles", "count": 25, "speed": [30, 70], "size": [2, 5], "opacity": 0.35}},
    "water_shimmer": {"type": "shimmer", "mask": "water", "params": {"amplitude": 2.5, "axis": "x"}},
    "sway": {"type": "shimmer", "mask": "foliage", "params": {"amplitude": 1.2, "scale": 6, "speed": 3}},
    "clouds": {"type": "fog", "mask": "sky", "params": {"kind": "clouds", "density": 0.35, "speed": 5, "color": "#EEE5D5"}},
    "ambient": {"type": "glow", "mask": None, "params": {"kind": "ambient", "amount": 0.025}},
}


def scene(audio_keys: list[str], fx_keys: list[str]) -> dict:
    layers, seen = [], set()
    for k in audio_keys:
        for l in AUDIO[k]:
            if l["id"] not in seen:
                layers.append(copy.deepcopy(l))
                seen.add(l["id"])
    effects = [dict(copy.deepcopy(FX[k]), id=k, seed=i + 1) for i, k in enumerate(fx_keys)]
    return {"audio": {"seed": 1, "layers": layers, "fade_in_s": 4, "fade_out_s": 12, "master_gain_db": 0.0},
            "animation": {"fit": "cover", "focus": [0.5, 0.5], "effects": effects, "masks": {}}}
