# YouTube setup

## A. Research (API key, read-only, free quota)
1. Go to https://console.cloud.google.com and create a project (e.g. "driftbound-studio").
2. APIs & Services → Library → enable **YouTube Data API v3** (and **YouTube Analytics API** for later).
3. Credentials → Create credentials → API key. Restrict it to "YouTube Data API v3".
4. Put it in `.env` as `DRIFTBOUND_YOUTUBE_API_KEY=...`, then restart.

Quota: the default is 10,000 units per day per project. The app counts `search.list` = 100 units and `videos.list` / `channels.list` = 1 unit,
and stops at the limit you set in Settings → Research (default 8,000). Verify current costs in the Cloud console quota page.
Retention: competitor data older than `retention_days` (30) is purged unless refreshed, in line with the YouTube API
Services developer policies. Re-check those policies yourself.

## B. Uploads (OAuth 2.0)
1. OAuth consent screen: User type **External**, publishing status *Testing*, add your Google account as a test user.
2. Credentials → Create credentials → OAuth client ID → **Desktop app**. Download the JSON to `secrets/client_secret.json`.
3. `cd backend && .venv/bin/pip install -e ".[youtube]"`
4. `cd backend && .venv/bin/python ../scripts/youtube_auth.py`. This opens a browser, then prints the connected channel name and ID.
5. Settings → Providers: `"youtube_publisher": "youtube"`. Settings → Publishing: set `made_for_kids_confirmed` to `true` or `false` yourself.
6. Analytics (separate, least privilege): `python ../scripts/youtube_auth.py analytics`.

Scopes: `youtube.upload`, `youtube.readonly`, `youtube` (thumbnails, playlists, publish status). Analytics uses `yt-analytics.readonly` in a separate token.

**Important platform limits** (verify current rules):
- Videos uploaded through an **unverified** API project created after 28 July 2020 are locked to *private*. To publish
  through the API you must pass Google's API audit. Until then, upload privately via the app and publish in YouTube Studio, or
  use the manual package.
- Uploading also consumes Data API quota.
- Monetization, ad settings, many channel settings and some metrics (e.g. eligible public watch hours) are **not available via the API**.

## C. Manual publishing fallback (no credentials needed)
After final approval, choose "Export YouTube upload package". You get `workspace/exports/<project>/` containing the MP4, `thumbnail.jpg`,
`title.txt`, `description.txt`, `tags.txt`, `metadata.json`, `manifest.json` and `CHECKLIST.md`. Upload in YouTube Studio as *Private*,
check the result, then publish.

## D. Disclosure and audience
- The app suggests whether to set "altered or synthetic content" (`status.containsSyntheticMedia`). YouTube requires it for
  realistic content that could be mistaken for real. Clearly fantastical scenes may not need it; follow current policy.
- "Made for kids" is never inferred from the category. You must confirm it.
