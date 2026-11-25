"""Procedural ambient effects (spec 16).

Seamless-loop design: every time-varying quantity is periodic in the loop length T (frames):
- particles travel an integer number of wraps per loop,
- flicker/twinkle use exactly periodic spectra (integer cycles per loop),
- slow fields (fog, clouds, caustics, shimmer) use two-phase flow blending, which allows any slow speed
  while frame T equals frame 0.
So a master of T frames repeats with no visible jump and no reversal.
Frames are float32 BGR in [0, 1].
"""
import cv2
import numpy as np

TAU = 2 * np.pi


def tileable_noise(h, w, scale, rng, octaves=3):
    """Periodic (tileable) smooth noise via spectral synthesis, normalized to [0, 1]."""
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    r = np.sqrt(fx ** 2 + fy ** 2) / max(scale, 1e-3)
    amp = np.exp(-(r ** 2)) + sum(0.5 ** o * np.exp(-((r / 2 ** o) ** 2)) for o in range(1, octaves))
    amp[0, 0] = 0
    spec = amp * np.exp(1j * rng.uniform(0, TAU, (h, w)))
    n = np.real(np.fft.ifft2(spec))
    n = (n - n.min()) / (np.ptp(n) + 1e-9)
    return n.astype(np.float32)


def periodic_signal(T, rng, low_cycles=1, high_cycles=None, slope=1.0):
    """1-D signal of length T, exactly periodic, energy between low and high cycles per loop, in [-1, 1]."""
    high = high_cycles or max(low_cycles + 1, T // 4)
    spec = np.zeros(T // 2 + 1, complex)
    k = np.arange(low_cycles, min(high, T // 2) + 1)
    spec[k] = (1 / k ** slope) * np.exp(1j * rng.uniform(0, TAU, len(k)))
    s = np.fft.irfft(spec, n=T)
    return (s / (np.abs(s).max() + 1e-9)).astype(np.float32)


def flow_sample(field, f, T, vx, vy, out_wh):
    """Two-phase flow: seamless loop of a field drifting at (vx, vy) px/frame (in field pixels)."""
    p1 = (f / T) % 1.0
    p2 = (p1 + 0.5) % 1.0
    w1, w2 = 1 - abs(2 * p1 - 1), 1 - abs(2 * p2 - 1)
    h, w = field.shape
    acc = 0
    for p, wt in ((p1, w1), (p2, w2)):
        off = (p - 0.5) * T  # frames of travel in this phase (centered => no seam)
        M = np.float32([[1, 0, vx * off], [0, 1, vy * off]])
        acc = acc + wt * cv2.warpAffine(field, M, (w, h), borderMode=cv2.BORDER_WRAP)
    mean = field.mean()
    out = mean + (acc - mean) / np.sqrt(w1 ** 2 + w2 ** 2)  # keep contrast constant across phases
    return cv2.resize(out.astype(np.float32), out_wh, interpolation=cv2.INTER_LINEAR)


def hex2bgr(c, default=(1, 1, 1)):
    if not c:
        return np.array(default, np.float32)
    c = c.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return np.array([b, g, r], np.float32)


class Effect:
    def __init__(self, w, h, T, fps, params, mask, seed, base):
        self.w, self.h, self.T, self.fps, self.p = w, h, T, fps, params
        self.mask = mask
        self.m3 = mask[..., None]
        self.rng = np.random.default_rng(seed)
        self.base = base
        self.intensity = float(params.get("intensity", 1.0))
        self.setup()

    def setup(self):
        pass

    def cycles(self, px_per_s, span):
        """Integer number of wraps per loop closest to the requested speed (>=1)."""
        return max(1, int(round(px_per_s * self.T / self.fps / span)))


class Particles(Effect):
    """Snow, rain, embers, dust, bubbles, underwater particles.

    params: kind(snow|rain|embers|dust|bubbles), count, size=[min,max] px, speed=[min,max] px/s,
            direction(down|up), wind px/s, sway px, color, opacity, depth_blur
    """

    def setup(self):
        p, w, h = self.p, self.w, self.h
        self.kind = p.get("kind", "snow")
        n = int(p.get("count", 400))
        self.span = h + 60
        depth = self.rng.uniform(0, 1, n) ** 1.5  # many far, few near
        smin, smax = p.get("size", [1.0, 4.0])
        vmin, vmax = p.get("speed", [20, 80])
        self.size = smin + (smax - smin) * depth
        speeds = vmin + (vmax - vmin) * depth
        self.k = np.array([self.cycles(v, self.span) for v in speeds])
        self.y0 = self.rng.uniform(0, self.span, n)
        self.x0 = self.rng.uniform(-40, w + 40, n)
        self.sway_m = self.rng.integers(1, 6, n)
        self.sway_ph = self.rng.uniform(0, TAU, n)
        self.sway = float(p.get("sway", 6)) * (0.4 + depth)
        wind = float(p.get("wind", 0))
        self.wind_k = np.round(wind * self.T / self.fps * depth / (w + 80))  # integer wraps horizontally
        self.alpha = (0.35 + 0.65 * depth) * float(p.get("opacity", 0.8))
        self.depth = depth
        self.flick_ph = self.rng.uniform(0, TAU, n)
        self.flick_k = self.rng.integers(3, 12, n) * max(1, self.T // (self.fps * 4))
        self.color = hex2bgr(p.get("color"), (1, 1, 1))
        self.down = p.get("direction", "up" if self.kind in ("embers", "bubbles") else "down") == "down"
        self.groups = np.digitize(depth, [0.33, 0.66])  # 3 blur layers
        self.angle = np.deg2rad(float(p.get("angle", 8)))

    def positions(self, f):
        ph = f / self.T
        travel = (self.y0 + self.k * self.span * ph) % self.span
        y = (travel if self.down else self.span - travel) - 30
        x = (self.x0 + self.wind_k * (self.w + 80) * ph + self.sway * np.sin(TAU * self.sway_m * ph + self.sway_ph))
        x = (x + 40) % (self.w + 80) - 40
        return x, y

    def __call__(self, frame, f):
        x, y = self.positions(f)
        ph = f / self.T
        out = frame
        for g in range(3):
            sel = self.groups == g
            if not sel.any():
                continue
            layer = np.zeros((self.h, self.w), np.float32)
            a = self.alpha[sel] * self.intensity
            if self.kind == "embers":
                a = a * (0.6 + 0.4 * np.sin(TAU * self.flick_k[sel] * ph + self.flick_ph[sel]))
                a = a * np.clip(y[sel] / (self.h * 0.6), 0, 1)  # fade out while rising
            for xi, yi, si, ai in zip(x[sel], y[sel], self.size[sel], a):
                if self.kind == "rain":
                    L = 6 + si * 10
                    dx, dy = np.sin(self.angle) * L, np.cos(self.angle) * L
                    cv2.line(layer, (int(xi * 4), int(yi * 4)), (int((xi + dx) * 4), int((yi + dy) * 4)),
                             float(ai), max(1, int(si * 0.6)), cv2.LINE_AA, shift=2)
                elif self.kind == "bubbles":
                    cv2.circle(layer, (int(xi * 4), int(yi * 4)), int(si * 4), float(ai), 1, cv2.LINE_AA, shift=2)
                else:
                    cv2.circle(layer, (int(xi * 4), int(yi * 4)), max(1, int(si * 2)), float(ai), -1, cv2.LINE_AA, shift=2)
            blur = (2 - g) * float(self.p.get("depth_blur", 1.2)) + 0.6
            layer = cv2.GaussianBlur(layer, (0, 0), blur)
            layer *= self.mask
            out = out * (1 - layer[..., None] * 0.15) + layer[..., None] * self.color  # light occlusion + add
        return out


class Stars(Effect):
    """Twinkling stars (new points + existing bright points in the masked sky), optional slow drift."""

    def setup(self):
        p, w, h = self.p, self.w, self.h
        n = int(p.get("count", 350) * float(self.mask.mean() + 0.05))
        self.k_drift = int(p.get("drift_wraps", 0))
        self.x0 = self.rng.uniform(0, w, n)
        self.y = self.rng.uniform(0, h, n)
        self.b = self.rng.uniform(0.2, 1.0, n) ** 2 * float(p.get("brightness", 0.9))
        self.r = self.rng.uniform(0.4, 1.4, n)
        self.tw_k = self.rng.integers(1, 8, n) * max(1, self.T // (self.fps * 6))
        self.tw_ph = self.rng.uniform(0, TAU, n)
        self.depth = float(p.get("twinkle", 0.35))
        gray = cv2.cvtColor((self.base * 255).astype(np.uint8), cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
        tophat = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((5, 5), np.uint8))
        self.existing = np.clip((tophat - 0.08) * 4, 0, 1) * self.mask  # small bright points already in the art
        self.ex_mod = tileable_noise(max(8, h // 16), max(8, w // 16), 6, self.rng)
        self.color = hex2bgr(p.get("color", "#E8EEFF"))

    def __call__(self, frame, f):
        ph = f / self.T
        layer = np.zeros((self.h, self.w), np.float32)
        x = (self.x0 + self.k_drift * self.w * ph) % self.w
        a = self.b * (1 - self.depth + self.depth * (0.5 + 0.5 * np.sin(TAU * self.tw_k * ph + self.tw_ph)))
        for xi, yi, ri, ai in zip(x, self.y, self.r, a):
            cv2.circle(layer, (int(xi * 4), int(yi * 4)), max(1, int(ri * 4)), float(ai), -1, cv2.LINE_AA, shift=2)
        layer = cv2.GaussianBlur(layer, (0, 0), 0.8) * self.mask
        mod = flow_sample(self.ex_mod, f, self.T, 0.02, 0.0, (self.w, self.h))
        ex = self.existing * (mod - 0.5) * 2 * self.depth
        return frame + (layer[..., None] * self.color + ex[..., None] * frame) * self.intensity


class Fog(Effect):
    """Fog / mist / slowly moving clouds: drifting tileable noise blended toward a color inside the mask.
    params: kind(fog|clouds), density, scale, speed px/s, color, softness"""

    def setup(self):
        self.ds = 4
        fh, fw = self.h // self.ds, self.w // self.ds
        self.field = tileable_noise(fh, fw, float(self.p.get("scale", 4)), self.rng, octaves=4)
        self.vx = float(self.p.get("speed", 6)) / self.fps / self.ds
        self.vy = float(self.p.get("speed_y", 0)) / self.fps / self.ds
        self.color = hex2bgr(self.p.get("color", "#C8D2DC"))
        self.density = float(self.p.get("density", 0.35))
        self.clouds = self.p.get("kind", "fog") == "clouds"

    def __call__(self, frame, f):
        n = flow_sample(self.field, f, self.T, self.vx, self.vy, (self.w, self.h))
        lo, hi = (0.45, 0.8) if self.clouds else (0.2, 0.9)
        a = np.clip((n - lo) / (hi - lo), 0, 1)
        a = a * a * (3 - 2 * a) * self.density * self.intensity * self.mask
        return frame * (1 - a[..., None]) + self.color * a[..., None]


class Glow(Effect):
    """Fireplace glow / candle flicker / subtle lighting variation inside the (blurred) mask.
    params: kind(fire|candle|ambient), amount, color, radius (fraction of width)"""

    def setup(self):
        kind = self.p.get("kind", "fire")
        secs = self.T / self.fps
        hi_hz = {"fire": 4.0, "candle": 7.0, "ambient": 0.05}[kind]
        lo_hz = {"fire": 0.05, "candle": 0.1, "ambient": 1 / secs}[kind]
        self.sig = periodic_signal(self.T, self.rng, max(1, int(lo_hz * secs)), max(2, int(hi_hz * secs)),
                                   slope=0.7 if kind != "ambient" else 1.5)
        rad = float(self.p.get("radius", 0.06)) * self.w
        self.area = cv2.GaussianBlur(self.mask, (0, 0), max(1, rad))
        self.area /= self.area.max() + 1e-6
        self.color = hex2bgr(self.p.get("color", {"fire": "#FF9A40", "candle": "#FFC070", "ambient": "#FFFFFF"}[kind]))
        self.amount = float(self.p.get("amount", {"fire": 0.18, "candle": 0.12, "ambient": 0.03}[kind]))
        self.kind = kind

    def __call__(self, frame, f):
        s = self.sig[f % self.T] * self.amount * self.intensity
        a = (s * self.area)[..., None]
        if self.kind == "ambient":
            return frame * (1 + a)
        return frame * (1 + a) + np.maximum(a, 0) * self.color * 0.35


class Caustics(Effect):
    """Underwater light patterns: bright ridges where two drifting noise fields cross."""

    def setup(self):
        self.ds = 3
        fh, fw = self.h // self.ds, self.w // self.ds
        sc = float(self.p.get("scale", 10))
        self.a = tileable_noise(fh, fw, sc, self.rng, 2)
        self.b = tileable_noise(fh, fw, sc * 1.3, self.rng, 2)
        v = float(self.p.get("speed", 10)) / self.fps / self.ds
        self.va, self.vb = (v, v * 0.4), (-v * 0.6, v * 0.8)
        self.color = hex2bgr(self.p.get("color", "#BDF4FF"))
        self.strength = float(self.p.get("strength", 0.12))

    def __call__(self, frame, f):
        a = flow_sample(self.a, f, self.T, *self.va, (self.w, self.h))
        b = flow_sample(self.b, f, self.T, *self.vb, (self.w, self.h))
        c = np.clip(1 - np.abs(a - b) * float(self.p.get("sharpness", 9)), 0, 1) ** 3
        return frame + (c * self.mask * self.strength * self.intensity)[..., None] * self.color


class Shimmer(Effect):
    """Water reflections / gentle vegetation sway: noise-driven displacement inside the mask.
    params: amplitude px, scale, speed px/s, axis(x|y|both)"""

    def setup(self):
        self.ds = 4
        fh, fw = self.h // self.ds, self.w // self.ds
        sc = float(self.p.get("scale", 12))
        self.nx = tileable_noise(fh, fw, sc, self.rng, 2)
        self.ny = tileable_noise(fh, fw, sc, self.rng, 2)
        self.v = float(self.p.get("speed", 8)) / self.fps / self.ds
        self.amp = float(self.p.get("amplitude", 3.0))
        axis = self.p.get("axis", "both")
        self.ax, self.ay = (1.0 if axis in ("x", "both") else 0.0), (1.0 if axis in ("y", "both") else 0.0)
        gx, gy = np.meshgrid(np.arange(self.w, dtype=np.float32), np.arange(self.h, dtype=np.float32))
        self.gx, self.gy = gx, gy

    def __call__(self, frame, f):
        dx = (flow_sample(self.nx, f, self.T, self.v, 0.1 * self.v, (self.w, self.h)) - 0.5) * 2 * self.amp * self.ax
        dy = (flow_sample(self.ny, f, self.T, -0.3 * self.v, self.v, (self.w, self.h)) - 0.5) * 2 * self.amp * self.ay
        m = self.mask * self.intensity
        warped = cv2.remap(frame, self.gx + dx * m, self.gy + dy * m, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        return warped


class WindowDroplets(Effect):
    """Rain on glass: static refractive droplets + a few drops sliding down (integer wraps per loop)."""

    def setup(self):
        w, h = self.w, self.h
        n = int(self.p.get("count", 260))
        dx = np.zeros((h, w), np.float32)
        dy = np.zeros((h, w), np.float32)
        hl = np.zeros((h, w), np.float32)
        ys, xs = np.nonzero(self.mask > 0.5)
        if len(xs):
            pick = self.rng.integers(0, len(xs), n)
            for x, y, r in zip(xs[pick], ys[pick], self.rng.uniform(1.5, 6, n)):
                ri = int(np.ceil(r))
                y0, y1, x0, x1 = max(0, y - ri), min(h, y + ri + 1), max(0, x - ri), min(w, x + ri + 1)
                yy, xx = np.mgrid[y0:y1, x0:x1]
                d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / r
                inside = d < 1
                lens = np.where(inside, (1 - d ** 2), 0)
                dx[y0:y1, x0:x1] += (xx - x) * lens * 0.9
                dy[y0:y1, x0:x1] += (yy - y) * lens * 0.9
                hl[y0:y1, x0:x1] += np.where(inside, np.clip(1 - np.hypot(xx - (x - r * 0.35), yy - (y - r * 0.35)) / (r * 0.4), 0, 1), 0)
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        self.mx, self.my = gx + dx, gy + dy
        self.hl = np.clip(hl, 0, 1) * 0.35
        k = int(self.p.get("sliders", 10))
        self.sx = self.rng.uniform(0, w, k)
        self.sy0 = self.rng.uniform(0, h, k)
        self.sk = np.array([self.cycles(v, h) for v in self.rng.uniform(25, 70, k)])
        self.sr = self.rng.uniform(2.5, 4.5, k)

    def __call__(self, frame, f):
        lensed = cv2.remap(frame, self.mx, self.my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        out = frame * (1 - self.m3) + lensed * self.m3 + (self.hl * self.mask)[..., None]
        slide = np.zeros((self.h, self.w), np.float32)
        ph = f / self.T
        for x, y0, k, r in zip(self.sx, self.sy0, self.sk, self.sr):
            y = (y0 + k * self.h * ph) % self.h
            cv2.ellipse(slide, (int(x * 4), int(y * 4)), (int(r * 4), int(r * 5)), 0, 0, 360, 0.25, -1, cv2.LINE_AA, shift=2)
            cv2.line(slide, (int(x * 4), int((y - 40) * 4)), (int(x * 4), int(y * 4)), 0.06, 2, cv2.LINE_AA, shift=2)
        slide = cv2.GaussianBlur(slide, (0, 0), 1.0) * self.mask
        return out + slide[..., None] * self.intensity


EFFECTS = {
    "particles": Particles, "stars": Stars, "fog": Fog, "glow": Glow, "caustics": Caustics,
    "shimmer": Shimmer, "window_droplets": WindowDroplets,
}
