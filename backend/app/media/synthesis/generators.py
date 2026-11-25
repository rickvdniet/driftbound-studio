"""Procedural environmental sound generators (spec 20).

Every layer is a stateful, seeded stream: render(n) returns float32 (n, 2) and keeps filter state and
pending events between calls, so 8 hours can be generated chunk by chunk with constant memory.
Determinism: the mixer always pulls fixed-size chunks, so the first 60 s of a final render are
sample-identical to the approved 60 s preview.
"""
import numpy as np
from scipy import signal

TWO_PI = 2 * np.pi


class Filter:
    """Stateful SOS filter for a stereo stream."""

    def __init__(self, sos):
        self.sos = sos
        self.zi = None

    def __call__(self, x):
        if self.zi is None:
            self.zi = np.zeros((self.sos.shape[0], 2, x.shape[1]))
        y, self.zi = signal.sosfilt(self.sos, x, axis=0, zi=self.zi)
        return y

    def set(self, sos):  # coefficient change, keep state (fine for slow parameter motion)
        self.sos = sos


def sos(kind, f, sr, order=2):
    nyq = sr / 2
    if kind == "band":
        lo, hi = max(10, f[0]), min(f[1], nyq * 0.95)
        return signal.butter(order, [lo, hi], btype="bandpass", fs=sr, output="sos")
    return signal.butter(order, min(f, nyq * 0.95), btype=kind, fs=sr, output="sos")


class SmoothRandom:
    """Band-limited random control signal in [-1, 1]; new target every 1/rate seconds, cosine interpolated."""

    def __init__(self, rng, rate_hz, sr):
        self.rng, self.step, self.sr = rng, max(1, int(sr / max(rate_hz, 1e-4))), sr
        self.a, self.b, self.pos = rng.uniform(-1, 1), rng.uniform(-1, 1), 0

    def __call__(self, n):
        out = np.empty(n, np.float32)
        i = 0
        while i < n:
            k = min(n - i, self.step - self.pos)
            x = (self.pos + np.arange(k)) / self.step
            w = 0.5 - 0.5 * np.cos(np.pi * x)
            out[i:i + k] = self.a + (self.b - self.a) * w
            self.pos += k
            i += k
            if self.pos >= self.step:
                self.a, self.b, self.pos = self.b, self.rng.uniform(-1, 1), 0
        return out


class Noise:
    PINK_B = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    PINK_A = [1, -2.494956002, 2.017265875, -0.522189400]

    def __init__(self, rng, color="pink", correlation=0.0):
        self.rng, self.color, self.corr = rng, color, correlation
        self.zi = None

    def __call__(self, n):
        w = self.rng.standard_normal((n, 2))
        if self.corr:
            w[:, 1] = self.corr * w[:, 0] + np.sqrt(1 - self.corr ** 2) * w[:, 1]
        if self.color == "white":
            return w * 0.3
        b, a = (self.PINK_B, self.PINK_A) if self.color == "pink" else ([0.02], [1, -0.998])
        if self.zi is None:
            self.zi = np.zeros((max(len(a), len(b)) - 1, 2))
        y, self.zi = signal.lfilter(b, a, w, axis=0, zi=self.zi)
        return y * (1.2 if self.color == "pink" else 1.0)


class Layer:
    def __init__(self, sr=48000, seed=0, **p):
        self.sr, self.p = sr, p
        self.rng = np.random.default_rng(seed)
        self.t = 0  # samples rendered
        self.setup()

    def setup(self):
        pass

    def render(self, n) -> np.ndarray:
        y = self.gen(n)
        self.t += n
        return y.astype(np.float32)


class EventLayer(Layer):
    """Base for layers made of discrete events (drops, clacks, thunder) with overlap across chunks."""
    rate_per_s = 1.0

    def setup(self):
        self.tail = np.zeros((0, 2))
        self.bed = None

    def event(self) -> np.ndarray:
        raise NotImplementedError

    def times(self, n):
        k = self.rng.poisson(self.rate_per_s * n / self.sr)
        return np.sort(self.rng.integers(0, n, k))

    def gen(self, n):
        evs = [(s, self.event()) for s in self.times(n)]
        maxlen = max([len(e) + s for s, e in evs] + [len(self.tail), n])
        buf = np.zeros((maxlen, 2))
        buf[:len(self.tail)] += self.tail
        for s, e in evs:
            buf[s:s + len(e)] += e
        self.tail = buf[n:]
        out = buf[:n]
        return out + (self.bed(n) if self.bed else 0)

    def pan(self, mono, pos):
        th = (pos + 1) * np.pi / 4
        return np.stack([mono * np.cos(th), mono * np.sin(th)], axis=1) * np.sqrt(2)

    def decay(self, ms, tau_ms):
        m = max(8, int(self.sr * ms / 1000))
        return np.exp(-np.arange(m) / (self.sr * tau_ms / 1000))


# ---------------------------------------------------------------- continuous layers

class NoiseLayer(Layer):
    """White / pink / brown noise with optional band limits. params: color, highpass, lowpass, correlation."""

    def setup(self):
        self.src = Noise(self.rng, self.p.get("color", "pink"), self.p.get("correlation", 0.0))
        self.f = []
        if self.p.get("highpass"):
            self.f.append(Filter(sos("highpass", self.p["highpass"], self.sr)))
        if self.p.get("lowpass"):
            self.f.append(Filter(sos("lowpass", self.p["lowpass"], self.sr)))

    def gen(self, n):
        y = self.src(n)
        for f in self.f:
            y = f(y)
        return y


class HumLayer(Layer):
    """Mechanical / spaceship hum: drifting harmonic series + band-limited noise around the fundamental."""

    def setup(self):
        self.f0 = self.p.get("f0", 55.0)
        self.harm = self.p.get("harmonics", [1.0, 0.5, 0.3, 0.15, 0.08])
        self.ph = self.rng.uniform(0, TWO_PI, (len(self.harm), 2))
        self.drift = SmoothRandom(self.rng, 0.05, self.sr)
        self.amp = [SmoothRandom(self.rng, 0.1 + 0.03 * i, self.sr) for i in range(len(self.harm))]
        self.noise = Noise(self.rng, "pink")
        self.nf = Filter(sos("band", (self.f0 * 0.7, self.f0 * 6), self.sr))
        self.detune = np.array([1.0, 1.0 + self.p.get("stereo_detune", 0.002)])

    def gen(self, n):
        f = self.f0 * (1 + self.p.get("drift", 0.004) * self.drift(n))
        y = np.zeros((n, 2))
        for i, a in enumerate(self.harm):
            inc = TWO_PI * (i + 1) * f[:, None] * self.detune[None, :] / self.sr
            ph = self.ph[i] + np.cumsum(inc, axis=0)
            self.ph[i] = ph[-1] % TWO_PI
            y += a * (1 + 0.25 * self.amp[i](n))[:, None] * np.sin(ph)
        return 0.25 * y + self.p.get("noise_mix", 0.6) * self.nf(self.noise(n))


class VentilationLayer(Layer):
    """Airflow: band-passed pink noise, a soft duct resonance and slow airflow modulation."""

    def setup(self):
        self.noise = Noise(self.rng, "pink", 0.3)
        self.band = Filter(sos("band", (self.p.get("low", 250), self.p.get("high", 2500)), self.sr))
        r = self.p.get("resonance_hz", float(self.rng.uniform(180, 420)))
        self.res = Filter(sos("band", (r * 0.92, r * 1.08), self.sr))
        self.mod = SmoothRandom(self.rng, 0.08, self.sr)

    def gen(self, n):
        x = self.noise(n)
        y = self.band(x) + 2.5 * self.res(x)
        return y * (1 + self.p.get("modulation", 0.15) * self.mod(n))[:, None]


class WindLayer(Layer):
    """Wind: noise through a slowly sweeping band-pass with gust envelopes."""
    BLOCK = 1024

    def setup(self):
        self.noise = Noise(self.rng, "pink", 0.2)
        self.center = SmoothRandom(self.rng, 0.07, self.sr)
        self.gust = SmoothRandom(self.rng, self.p.get("gust_rate", 0.12), self.sr)
        self.lo, self.hi = self.p.get("low", 150), self.p.get("high", 900)
        self.flt = Filter(sos("band", (self.lo, self.lo * 2.2), self.sr))

    def gen(self, n):
        x, c, g = self.noise(n), self.center(n), self.gust(n)
        y = np.empty_like(x)
        for i in range(0, n, self.BLOCK):
            fc = self.lo + (self.hi - self.lo) * (0.5 + 0.5 * c[i])
            self.flt.set(sos("band", (fc * 0.6, fc * 1.6), self.sr))
            y[i:i + self.BLOCK] = self.flt(x[i:i + self.BLOCK])
        env = 0.55 + self.p.get("gustiness", 0.4) * g
        return 2.0 * y * np.clip(env, 0.1, 1.5)[:, None]


class OceanLayer(Layer):
    """Ocean: independent per-channel wave envelopes over low/mid noise beds plus foam wash."""

    def setup(self):
        self.noise = Noise(self.rng, "brown")
        self.hiss = Noise(self.rng, "pink")
        self.lp = Filter(sos("lowpass", self.p.get("body_lowpass", 900), self.sr))
        self.wash = Filter(sos("band", (1200, 6000), self.sr))
        self.waves = [self._new_wave(start=-int(self.rng.uniform(0, 8) * self.sr)) for _ in range(2)]
        self.intensity = SmoothRandom(self.rng, 1 / 90, self.sr)

    def _new_wave(self, start):
        return {"start": start, "len": int(self.rng.uniform(*self.p.get("period", (7, 13))) * self.sr),
                "amp": self.rng.uniform(0.6, 1.0)}

    def _env(self, ch, n):
        env = np.zeros(n)
        i = 0
        while i < n:
            w = self.waves[ch]
            pos = self.t + i - w["start"]
            if pos >= w["len"]:
                self.waves[ch] = self._new_wave(self.t + i)
                continue
            k = min(n - i, w["len"] - pos)
            x = (pos + np.arange(k)) / w["len"]
            # slow swell rising for ~65%, then a softer recession
            shape = np.where(x < 0.65, np.sin(np.pi / 2 * x / 0.65) ** 2, np.cos(np.pi / 2 * np.clip((x - 0.65) / 0.35, 0, 1)) ** 1.5)
            env[i:i + k] = 0.15 + w["amp"] * shape
            i += k
        return env

    def gen(self, n):
        env = np.stack([self._env(0, n), self._env(1, n)], axis=1)
        inten = (1 + 0.2 * self.intensity(n))[:, None]
        body = self.lp(self.noise(n)) * env
        foam = self.wash(self.hiss(n)) * env ** 2
        return (2.2 * body + 0.9 * foam) * inten


class DroneLayer(Layer):
    """Low atmospheric texture: slowly breathing partials + filtered air noise."""

    def setup(self):
        f0 = self.p.get("f0", 73.4)
        self.freqs = [f0 * r for r in self.p.get("ratios", [1, 1.5, 2, 3])]
        self.ph = self.rng.uniform(0, TWO_PI, (len(self.freqs), 2))
        self.amps = [SmoothRandom(self.rng, 1 / self.rng.uniform(12, 30), self.sr) for _ in self.freqs]
        self.noise = Noise(self.rng, "brown", 0.1)
        self.lp = Filter(sos("lowpass", self.p.get("air_lowpass", 500), self.sr))

    def gen(self, n):
        y = np.zeros((n, 2))
        for i, f in enumerate(self.freqs):
            inc = TWO_PI * f * np.array([1.0, 1.0007]) / self.sr
            ph = self.ph[i] + inc[None, :] * np.arange(1, n + 1)[:, None]
            self.ph[i] = ph[-1] % TWO_PI
            y += (0.5 + 0.5 * self.amps[i](n))[:, None] * np.sin(ph) / (i + 1)
        return 0.2 * y + 0.8 * self.lp(self.noise(n))


# ---------------------------------------------------------------- event layers

class RainLayer(EventLayer):
    """Rain: soft broadband hiss + individually synthesized droplet impacts with random pan and pitch."""

    def setup(self):
        super().setup()
        self.rate_per_s = self.p.get("drops_per_second", 120)
        noise = Noise(self.rng, "pink", 0.1)
        hp = Filter(sos("highpass", self.p.get("hiss_highpass", 400), self.sr))
        lp = Filter(sos("lowpass", self.p.get("hiss_lowpass", 8000), self.sr))
        mod = SmoothRandom(self.rng, 1 / 40, self.sr)
        hiss = self.p.get("hiss", 0.6)
        self.bed = lambda n: hiss * lp(hp(noise(n))) * (1 + 0.15 * mod(n))[:, None]

    def event(self):
        d = self.decay(self.rng.uniform(4, 25), self.rng.uniform(1.0, 5.0))
        f = self.rng.uniform(*self.p.get("drop_band", (1500, 6500)))
        b = sos("band", (f * 0.7, f * 1.3), self.sr)
        mono = signal.sosfilt(b, self.rng.standard_normal(len(d))) * d
        amp = np.exp(self.rng.normal(-1.5, 0.6)) * self.p.get("drop_level", 0.6)
        return self.pan(mono * amp, self.rng.uniform(-0.9, 0.9))


class FireLayer(EventLayer):
    """Fireplace approximation: low roar with flicker + crackles and occasional soft pops.
    Synthetic; for authentic crackle prefer a licensed recording (see licensing guide)."""

    def setup(self):
        super().setup()
        self.rate_per_s = self.p.get("crackles_per_second", 9)
        noise = Noise(self.rng, "brown", 0.4)
        lp = Filter(sos("lowpass", 350, self.sr))
        flick = SmoothRandom(self.rng, 3.0, self.sr)
        roar = self.p.get("roar", 0.8)
        self.bed = lambda n: roar * 2.5 * lp(noise(n)) * (1 + 0.35 * flick(n))[:, None]

    def event(self):
        pop = self.rng.random() < 0.08
        d = self.decay(40 if pop else self.rng.uniform(2, 8), 12 if pop else self.rng.uniform(0.3, 1.5))
        f = self.rng.uniform(300, 900) if pop else self.rng.uniform(1500, 5000)
        mono = signal.sosfilt(sos("band", (f * 0.6, f * 1.6), self.sr), self.rng.standard_normal(len(d))) * d
        amp = np.exp(self.rng.normal(-1.8, 0.7)) * (0.5 if pop else 1.0)
        return self.pan(mono * amp * self.p.get("crackle_level", 0.7), self.rng.uniform(-0.4, 0.4))


class RhythmLayer(EventLayer):
    """Rhythmic mechanical sounds (e.g. rail joints): periodic clack pairs with jitter over a rumble bed."""

    def setup(self):
        super().setup()
        self.period = self.p.get("period_s", 1.8)
        self.spacing = self.p.get("pair_spacing_s", 0.14)
        self.next = int(self.rng.uniform(0, self.period) * self.sr)
        noise = Noise(self.rng, "brown", 0.6)
        lp = Filter(sos("lowpass", self.p.get("rumble_lowpass", 180), self.sr))
        speed = SmoothRandom(self.rng, 1 / 60, self.sr)
        self.speed = speed
        rumble = self.p.get("rumble", 0.9)
        self.bed = lambda n: rumble * 3 * lp(noise(n))

    def times(self, n):
        out = []
        while self.next < self.t + n:
            s = self.next - self.t
            out += [s, s + int(self.spacing * self.sr)]
            jitter = 1 + 0.03 * self.rng.standard_normal() + 0.05 * float(self.speed(1)[0])
            self.next += int(self.period * jitter * self.sr)
        return [max(0, s) for s in out]

    def event(self):
        d = self.decay(120, 25)
        thump = np.sin(TWO_PI * self.rng.uniform(55, 85) * np.arange(len(d)) / self.sr) * d
        click = signal.sosfilt(sos("band", (400, 2200), self.sr), self.rng.standard_normal(len(d))) * d ** 3
        return self.pan((0.8 * thump + 0.4 * click) * self.p.get("clack_level", 0.5), self.rng.uniform(-0.2, 0.2))


class ThunderLayer(EventLayer):
    """Distant thunder: rare, slow-attack, low-passed rumbles (no sharp cracks: safe for sleep)."""

    def setup(self):
        super().setup()
        self.rate_per_s = self.p.get("per_minute", 0.6) / 60

    def event(self):
        dur = self.rng.uniform(6, 14)
        n = int(dur * self.sr)
        t = np.arange(n) / self.sr
        att = self.rng.uniform(0.4, 1.2)
        env = np.minimum(t / att, 1) ** 2 * np.exp(-np.maximum(t - att, 0) / (dur / 3.5))
        rumble = signal.sosfilt(sos("lowpass", self.rng.uniform(140, 320), self.sr), np.cumsum(self.rng.standard_normal(n)) * 0.02)
        am = 1 + 0.5 * np.sin(TWO_PI * self.rng.uniform(0.5, 2) * t + self.rng.uniform(0, 6))
        mono = rumble * env * am * self.p.get("level", 0.8)
        return self.pan(mono, self.rng.uniform(-0.6, 0.6))


class UnderwaterLayer(EventLayer):
    """Underwater: deep muffled pressure bed + occasional soft rising bubble blips."""

    def setup(self):
        super().setup()
        self.rate_per_s = self.p.get("bubbles_per_second", 0.7)
        noise = Noise(self.rng, "brown", 0.3)
        lp = Filter(sos("lowpass", self.p.get("lowpass", 320), self.sr))
        mod = SmoothRandom(self.rng, 0.06, self.sr)
        self.bed = lambda n: 4.0 * lp(noise(n)) * (1 + 0.3 * mod(n))[:, None]

    def event(self):
        dur = self.rng.uniform(0.03, 0.09)
        n = int(dur * self.sr)
        t = np.arange(n) / self.sr
        f = self.rng.uniform(250, 600) * (1 + 2.0 * t / dur)
        mono = np.sin(TWO_PI * np.cumsum(f) / self.sr) * np.sin(np.pi * t / dur) ** 2
        mono = signal.sosfilt(sos("lowpass", 1500, self.sr), mono) * np.exp(self.rng.normal(-2.0, 0.5))
        return self.pan(mono * self.p.get("bubble_level", 0.6), self.rng.uniform(-0.8, 0.8))


GENERATORS = {
    "noise": NoiseLayer, "hum": HumLayer, "ventilation": VentilationLayer, "wind": WindLayer, "ocean": OceanLayer,
    "drone": DroneLayer, "rain": RainLayer, "fire": FireLayer, "rhythm": RhythmLayer, "thunder": ThunderLayer,
    "underwater": UnderwaterLayer,
}
