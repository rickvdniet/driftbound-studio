"""Drive the 'Sleeping Near Saturn' concept through the full local pipeline via the running API.

Usage (API + worker running):  python scripts/demo_saturn.py [render_seconds]
Approvals are given automatically here because this is a demo; in normal use you approve in the dashboard.
"""
import sys
import time

import httpx

B = "http://127.0.0.1:8000/api"
c = httpx.Client(timeout=60)


def wait(pid, r):
    r.raise_for_status()
    jid = r.json()["id"]
    while True:
        j = next(j for j in c.get(f"{B}/projects/{pid}").json()["jobs"] if j["id"] == jid)
        if j["status"] in ("done", "failed", "cancelled"):
            print(f"  job {j['type']}: {j['status']} {j.get('error') or ''}", flush=True)
            if j["status"] != "done":
                sys.exit(1)
            return
        time.sleep(5)


seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 600
con = next(x for x in c.get(f"{B}/concepts").json() if x["name"] == "Sleeping Near Saturn")
c.post(f"{B}/concepts/{con['id']}/status", json={"status": "approved"})
p = c.post(f"{B}/concepts/{con['id']}/to-project").json()
pid = p["id"]
print("project", pid, flush=True)
wait(pid, c.post(f"{B}/projects/{pid}/images/generate", json={"provider": "procedural", "count": 2}))
img = next(a for a in c.get(f"{B}/projects/{pid}").json()["assets"] if a["kind"] == "image")
c.post(f"{B}/projects/{pid}/images/{img['id']}/approve")
t = time.time(); wait(pid, c.post(f"{B}/projects/{pid}/preview", json={})); print(f"  preview {time.time() - t:.0f}s", flush=True)
c.post(f"{B}/projects/{pid}/preview/approve").raise_for_status()
t = time.time(); wait(pid, c.post(f"{B}/projects/{pid}/render", json={"duration_s": seconds})); print(f"  render+QA {time.time() - t:.0f}s", flush=True)
d = c.get(f"{B}/projects/{pid}").json()
print("state", d["state"], "QA", d["data"]["qa_technical"]["status"], d["data"]["qa_technical"]["warnings"], d["data"]["qa_technical"]["errors"])
