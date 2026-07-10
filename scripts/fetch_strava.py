#!/usr/bin/env python3
"""Fetch 2026 activities from the Strava API and write data/current.json.

Runs in GitHub Actions. Requires env vars (set as repo secrets):
  STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
"""
import json, os, sys, time, urllib.parse, urllib.request

CLIENT_ID = os.environ["STRAVA_CLIENT_ID"]
CLIENT_SECRET = os.environ["STRAVA_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["STRAVA_REFRESH_TOKEN"]

# Only activities on/after this date come from Strava; earlier dates come
# from the static Garmin export (data/history.json).
CUTOVER = "2026-01-01"
CUTOVER_EPOCH = 1767225600  # 2026-01-01 00:00 UTC

M_PER_MI = 1609.344
YD_PER_M = 1.0936133


def post(url, params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data)) as r:
        return json.load(r)


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def sport_of(a):
    t = a.get("sport_type") or a.get("type") or ""
    if t in ("Run", "VirtualRun", "TrailRun"):
        return "run"
    if t in ("Ride", "VirtualRide", "MountainBikeRide", "GravelRide", "EBikeRide"):
        return "bike"
    if t in ("Swim",):
        return "swim"
    return "other"


def main():
    tok = post("https://www.strava.com/oauth/token", {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
    })
    token = tok["access_token"]

    acts, page = [], 1
    while True:
        batch = get(
            "https://www.strava.com/api/v3/athlete/activities"
            f"?after={CUTOVER_EPOCH}&per_page=200&page={page}",
            token,
        )
        if not batch:
            break
        acts.extend(batch)
        page += 1
        if page > 20:  # safety cap
            break

    out = []
    for a in acts:
        s = sport_of(a)
        dist_m = a.get("distance") or 0
        dist = round(dist_m * YD_PER_M) if s == "swim" else round(dist_m / M_PER_MI, 2)
        out.append({
            "d": (a.get("start_date_local") or "")[:10],
            "s": s,
            "m": round((a.get("moving_time") or 0) / 60, 1),
            "dist": dist,
            "t": (a.get("name") or "")[:40],
        })
    out = [o for o in out if o["d"] >= CUTOVER]
    out.sort(key=lambda o: o["d"])

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "acts": out,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/current.json", "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"Wrote {len(out)} activities to data/current.json")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as e:
        print(f"Strava API error {e.code}: {e.read().decode()[:500]}", file=sys.stderr)
        sys.exit(1)
