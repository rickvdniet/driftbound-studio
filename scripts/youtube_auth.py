"""Connect your YouTube channel (OAuth 2.0, installed-app flow). Run once on your own computer:

    cd backend && .venv/bin/python ../scripts/youtube_auth.py            # upload + manage scopes
    cd backend && .venv/bin/python ../scripts/youtube_auth.py analytics  # analytics read scope (separate)

Requires: pip install -e ".[youtube]" and secrets/client_secret.json (OAuth client of type "Desktop app").
The token is stored in secrets/ (git-ignored) with file mode 600. Shows the connected channel before you upload.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.providers.youtube.publisher import ANALYTICS_SCOPE, MANAGE_SCOPE, READ_SCOPE, UPLOAD_SCOPE, YouTubePublisher  # noqa: E402

s = get_settings()
analytics = len(sys.argv) > 1 and sys.argv[1] == "analytics"
scopes = [ANALYTICS_SCOPE, READ_SCOPE] if analytics else [UPLOAD_SCOPE, READ_SCOPE, MANAGE_SCOPE]
flow = InstalledAppFlow.from_client_secrets_file(str(s.youtube_client_secrets), scopes)
creds = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
target = s.youtube_token_file.with_name("youtube_analytics_token.json") if analytics else s.youtube_token_file
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(creds.to_json())
target.chmod(0o600)
if not analytics:
    ch = YouTubePublisher().channel()
    print(f"Connected channel: {ch['title']} ({ch['id']})")
print(f"Token saved to {target}")
