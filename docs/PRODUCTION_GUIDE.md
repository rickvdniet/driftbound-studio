# Production guide

## Stages and gates
`CONCEPT_APPROVED → images → IMAGE_REVIEW → (approve) → masks/effects/layers → BUILDING_MASTERS → PREVIEW_READY →
(approve) → RENDERING → QUALITY_CHECK → FINAL_REVIEW → (approve) → READY_FOR_UPLOAD → UPLOADED_PRIVATE → (approve) →
PUBLISHED / SCHEDULED`.

Each approval stores a hash of the configuration it covers. Changing the image, effects or audio later invalidates the
preview approval and everything after it. A full render then refuses to start until you approve a new preview.
You can rebuild assets on their own: "Rebuild audio only" and "Rebuild visuals only" keep the other part.

## Animation (procedural, default)
The camera stays still. Every effect is **seamless by construction** over the loop length (default 60 s):
- Particles (rain, snow, embers, dust, bubbles) travel a whole number of screen heights per loop. Speeds are rounded to the nearest whole-number value.
- Flicker and twinkle use exactly periodic spectra.
- Slow fields (fog, clouds, caustics, water shimmer, vegetation sway) use *two-phase flow*: two offset copies crossfade with constant contrast, so any slow drift speed loops without a seam and without playing in reverse.

| Effect | Use for | Key params |
|---|---|---|
| `particles` kind `rain` | rain outside windows | count, speed [px/s], size, angle, opacity |
| `particles` kind `snow` / `dust` / `embers` / `bubbles` | snow, floating particles, fire embers, underwater | count, speed, size, sway, wind, direction, color |
| `window_droplets` | rain on glass (refraction + sliding drops) | count, sliders |
| `stars` | twinkle of new and existing stars, optional drift | count, twinkle, drift_wraps (0 = still) |
| `fog` kind `fog` / `clouds` | mist, slowly moving clouds | density, scale, speed, color |
| `glow` kind `fire` / `candle` / `ambient` | fireplace light, candles, gentle light breathing | amount, radius, color |
| `caustics` | underwater light patterns | strength, scale, speed, sharpness |
| `shimmer` | water reflections (`axis: x`), foliage sway (small amplitude) | amplitude px, scale, speed |

All effects also take `intensity`, `seed` and `mask`.
**Masks**: draw polygons on the approved image (normalized coordinates, so the mask is independent of resolution), import a PNG
(white = effect), use `rect`, `invert`, and `feather` (fraction of the frame width). Effects refer to masks by name.

The loop check compares the frame-to-frame difference across the loop boundary with the normal difference. A ratio
around 1.0 means seamless. Inspect the boundary yourself in the preview player too, since it loops.

## Audio synthesis & mixing
Generators (`backend/app/media/synthesis/generators.py`), each seeded and streamed in 1 s chunks:
`noise` (white/pink/brown), `hum` (drifting harmonics + noise, spaceship/mechanical), `ventilation`, `wind` (sweeping
band-pass + gusts), `ocean` (independent L/R wave envelopes + foam), `drone` (slow breathing partials), `rain` (hiss +
individually synthesized drops), `fire` (roar + crackles; synthetic approximation), `rhythm` (rail-joint clack pairs
with jitter), `thunder` (rare, slow-attack, low-passed: safe for sleep), `underwater` (pressure bed + bubbles).

Per layer: gain, pan, high-pass, low-pass, slow seeded volume variation (`variation_db`, `variation_period_s`), seed, mute/solo.
Master: profile low-pass, loudness target (sleep ≈ −20 LUFS, focus ≈ −18 LUFS; these are product defaults, not YouTube
rules), soft limiter at the true-peak ceiling, fade in and out.

**Loudness and reproducibility.** The preview job measures the raw mix once, computes a master gain, and caches it per audio-config
hash. The final render uses the same seeds, chunk size and gain, so its first 60 s are sample-identical to the
approved preview (`test_audio_determinism_and_chunking`).
Procedural layers never repeat, so an 8-hour video has no audible loop. Imported recordings loop with an equal-power
crossfade and a seeded start offset.

Previews: per-layer stems (play together with mute/solo), a 60 s mix, and an optional 10-minute "long audio check".

## Licensed recordings
Synthesis is weakest for birdsong, real crackling fire, streams and specific trains. Import recordings with:
license name, creator, title, source URL and evidence. Preferred: your own recordings, CC0, and CC-BY (attribution is added
to the description automatically). **Non-commercial or unclear licenses block final approval.** Never extract audio
from YouTube videos. Freesound and Pixabay assets must be checked one by one; "royalty-free" does not mean unrestricted.

## Rendering
1. Visual master: the approved image plus effects, rendered once (loop length × fps frames) to H.264 with closed GOPs.
2. Final: `ffmpeg -stream_loop -1 -i master.mp4` with **stream copy** for video. Audio is synthesized chunk by chunk and piped into
   AAC 192 kbps, 48 kHz. `-t` sets the exact duration and `+faststart` makes it web-optimized. Memory use stays flat.
3. Disk check before starting: the estimate is master size × repeats + audio bitrate × duration, plus a margin.
Durations offered: 30 s, 1 min, 10 min, 1, 2, 3, 4 and 8 h (YouTube's limit is 12 h; verify yours).

## QA
Technical (blocking unless noted): streams present, H.264/AAC, resolution, 16:9, 48 kHz stereo, duration, A/V stream
alignment, clean decode over a loop boundary, true peak, YouTube size and duration limits, no silence in the first 10 min.
Warnings: loudness target, loudness range, black or frozen frames in the master.
Creative: usage rights for every used asset, loop seamlessness, perceptual-hash similarity to other projects, artwork
reuse, metadata limits and health claims, thumbnail size. Final human approval is always required.

## SEO metadata
Five title candidates and one recommended title (≤100 characters), a description (environment, sounds, use, duration, credits,
AI-assistance note), and tags fitted to the 500-character limit. The playlist comes from the brand settings. Medical-claim words
("cures", "insomnia relief", ...) are flagged. Every edit is stored as a revision.

## Brand
All brand values (names, tagline, palette, channel description, playlists, thumbnail rules, watermark) live in
Settings → Brand. Thumbnails use the palette and Pillow's bundled font (Aileron, CC0). The handle `@DriftboundAmbience`
is **provisional**; availability is not checked by the app.
