# Providers, licenses and costs

## Provider priority (applied per task)
1. Local procedural generation → 2. local open models (license-checked) → 3. own or licensed assets →
4. free API quotas (YouTube Data API) → 5. manual imports from existing subscriptions → 6. paid APIs (disabled).

| Kind | Provider | Where | Cost | Status |
|---|---|---|---|---|
| LLM | templates | local | €0 | ✅ |
| LLM | Ollama | local | €0 (electricity) | 🟡 not verified live |
| Image | procedural painter | local CPU | €0 | ✅ space skies only |
| Image | import (own, licensed, or made in a ChatGPT/Midjourney/etc. subscription you already pay for) | – | allocated subscription | ✅ |
| Image | ComfyUI | local GPU | €0 | 🟡 |
| Video | procedural effects | local CPU | €0 | ✅ |
| Audio | synthesis, licensed import | local | €0 | ✅ |
| Research | YouTube Data API v3 | Google | €0 within quota | ✅ (mock-tested) |
| Publishing | YouTube Data API v3 (OAuth) | Google | €0 within quota | 🟡 |
| Paid | OpenAI, Runway, ElevenLabs | external | paid | interface only, disabled |

Consumer ChatGPT or Claude subscriptions do **not** include API access. Use them by pasting their output into the app
(concept JSON, metadata text, imported images).

## Model licenses (check the current license before downloading; summarized as understood at build time)
| Model | License | Commercial use |
|---|---|---|
| Qwen2.5-7B-Instruct | Apache-2.0 | yes |
| Llama 3.x | Llama Community License | yes, with conditions (e.g. >700M MAU clause, attribution) |
| SDXL base 1.0 | CreativeML Open RAIL++-M | yes, with use restrictions |
| FLUX.1 [schnell] | Apache-2.0 | yes |
| FLUX.1 [dev] | FLUX.1-dev Non-Commercial License | **no** (model); read the terms for outputs |
| Stable Diffusion 3.5 | Stability AI Community License | free below a revenue threshold; check terms |
| Real-ESRGAN | BSD-3-Clause | yes |
| Wan 2.1 / 2.2 (video) | Apache-2.0 | yes; check the model card |

## Budget guard (backend/app/services/budget.py)
A paid call goes through only if **all** of these are true: paid usage enabled (with explicit confirmation), provider
on the allow-list, explicit approval for this job, known price estimate, no duplicate request key, and the reservation fits
both the monthly and the per-project budget. Defaults are €0 and disabled, and paid fallback is off. External job IDs and
request keys are stored immediately, so a crash or retry cannot pay twice.

## Cost model
Tracked **separately** (Costs page):
- **API expenditure.** Actual or committed. €0 by default.
- **Electricity.** An estimate: render seconds × your configured watts × €/kWh. Never shown as measured.
- **Storage.** Workspace bytes per folder, plus free disk.
- **Existing subscriptions.** You enter them with an allocated share. They are not marginal cost.
- **Manual effort.** Optional hourly value for your own time.
- **Hardware investment.** Enter it as a subscription-like monthly amount if you want it in the totals.

Example (your numbers will differ): an 8 h video renders on a 4-thread CPU in about 6 min (master) plus ~25–40 min (audio
synthesis and assembly). At 65 W and €0.30/kWh that is about €0.01–0.02 of electricity. The file is ~2–4 GB at the default settings.
