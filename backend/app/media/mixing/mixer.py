"""Multilayer soundscape mixer (spec 23). Streams fixed-size chunks; never holds full-length audio in memory."""
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from app.config.settings import get_settings
from app.media.synthesis.generators import GENERATORS, Filter, Layer, SmoothRandom, sos

CHUNK_S = 1.0  # fixed chunk size => preview and final are sample-identical over the overlap


class FileLoopLayer(Layer):
    """Imported (licensed) recording, looped with an equal-power crossfade and a seeded start offset."""

    def setup(self):
        path, xf = Path(self.p["path"]), self.p.get("crossfade_s", 3.0)
        raw = subprocess.run([get_settings().ffmpeg, "-v", "error", "-i", str(path), "-t", "900", "-f", "f32le",
                              "-ac", "2", "-ar", str(self.sr), "-"], capture_output=True, check=True).stdout
        clip = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
        x = int(min(xf * self.sr, len(clip) // 3))
        if x > 0:
            t = np.linspace(0, np.pi / 2, x)[:, None]
            seg = clip[:len(clip) - x].copy()
            seg[:x] = clip[:x] * np.sin(t) + clip[len(clip) - x:] * np.cos(t)
        else:
            seg = clip
        self.loop = seg
        self.pos = int(self.rng.integers(0, max(1, len(seg))))

    def gen(self, n):
        idx = (self.pos + np.arange(n)) % len(self.loop)
        self.pos = (self.pos + n) % len(self.loop)
        return self.loop[idx]


class Channel:
    def __init__(self, spec: dict, sr: int, base_seed: int):
        cls = FileLoopLayer if spec["type"] == "file" else GENERATORS[spec["type"]]
        seed = int(spec.get("seed", 0)) + base_seed * 1000
        self.layer = cls(sr=sr, seed=seed, **spec.get("params", {}))
        self.gain = 10 ** (spec.get("gain_db", 0.0) / 20)
        th = (float(spec.get("pan", 0.0)) + 1) * np.pi / 4
        self.pan = np.array([np.cos(th), np.sin(th)]) * np.sqrt(2)
        self.filters = []
        if spec.get("highpass_hz"):
            self.filters.append(Filter(sos("highpass", spec["highpass_hz"], sr)))
        if spec.get("lowpass_hz"):
            self.filters.append(Filter(sos("lowpass", spec["lowpass_hz"], sr)))
        self.var_db = spec.get("variation_db", 1.5)
        self.var = SmoothRandom(np.random.default_rng(seed + 7), 1 / spec.get("variation_period_s", 45), sr)

    def render(self, n):
        y = self.layer.render(n)
        for f in self.filters:
            y = f(y)
        g = self.gain * 10 ** (self.var_db * self.var(n) / 20)
        return y * self.pan[None, :] * g[:, None]


def stream(audio_cfg: dict, duration_s: float, sr: int = 48000, only_layer: str | None = None, profile: dict | None = None):
    """Yield (n, 2) float32 chunks of the mix. Master gain, profile low-pass and start/end fades applied."""
    layers = [l for l in audio_cfg.get("layers", []) if not l.get("mute")]
    solo = [l for l in layers if l.get("solo")]
    if solo:
        layers = solo
    if only_layer:
        layers = [l for l in audio_cfg.get("layers", []) if l["id"] == only_layer]
    base_seed = int(audio_cfg.get("seed", 1))
    chans = [Channel(l, sr, base_seed) for l in layers]
    master = 10 ** (audio_cfg.get("master_gain_db", 0.0) / 20)
    lp = (profile or {}).get("lowpass_hz")
    mlp = Filter(sos("lowpass", lp, sr)) if lp and not only_layer else None
    total = int(duration_s * sr)
    fi, fo = int(audio_cfg.get("fade_in_s", 4) * sr), int(audio_cfg.get("fade_out_s", 10) * sr)
    chunk = int(CHUNK_S * sr)
    done = 0
    while done < total:
        y = np.zeros((chunk, 2))
        for c in chans:
            y += c.render(chunk)
        if mlp:
            y = mlp(y)
        n = min(chunk, total - done)
        y = y[:n] * master
        idx = done + np.arange(n)
        env = np.ones(n)
        if fi:
            env = np.minimum(env, np.sin(np.clip(idx / fi, 0, 1) * np.pi / 2) ** 2)
        if fo:
            env = np.minimum(env, np.sin(np.clip((total - idx) / fo, 0, 1) * np.pi / 2) ** 2)
        y *= env[:, None]
        done += n
        yield y.astype(np.float32)


def render_wav(audio_cfg: dict, duration_s: float, out: Path, sr=48000, only_layer=None, profile=None) -> Path:
    data = np.concatenate(list(stream(audio_cfg, duration_s, sr, only_layer, profile)))
    peak = float(np.abs(data).max()) if len(data) else 0.0
    if only_layer and peak > 0.98:  # stems are for listening only; keep them unclipped
        data *= 0.98 / peak
    wavfile.write(out, sr, data)
    return out


def safety_limit(x: np.ndarray, ceiling_db: float) -> np.ndarray:
    """Smooth soft-knee limiter for previews/finals (sample peak, applied before AAC encode)."""
    c = 10 ** (ceiling_db / 20)
    knee = 0.8 * c
    a = np.abs(x)
    over = a > knee
    y = x.copy()
    y[over] = np.sign(x[over]) * (knee + (c - knee) * np.tanh((a[over] - knee) / (c - knee)))
    return y
