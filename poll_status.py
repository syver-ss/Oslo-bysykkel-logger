#!/usr/bin/env python3
"""Poll Oslo Bysykkel GBFS station_status og skriv til data/status_YYYY-MM-DD.csv.
Kjøres av GitHub Actions (se .github/workflows/log-status.yml). Kun standardbibliotek."""
import csv, json, os, urllib.request
from datetime import datetime, timezone

BASE = "https://gbfs.urbansharing.com/oslobysykkel.no"
CLIENT_ID = os.environ.get("CLIENT_ID", "syver-stave-dtu-bachelor")   # KREVES av Oslo Bysykkel
HEADERS = {"Client-Identifier": CLIENT_ID, "User-Agent": f"{CLIENT_ID} (bachelor)"}
DATA = "data"
COLS = ["polled_at_utc", "station_id", "num_bikes_available", "num_docks_available",
        "is_renting", "is_returning", "is_installed", "last_reported"]


def fetch(feed):
    req = urllib.request.Request(f"{BASE}/{feed}.json", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["stations"]


def main():
    os.makedirs(DATA, exist_ok=True)
    try:
        stations = fetch("station_status")
    except Exception as e:
        print(f"station_status feilet: {e}")     # ingen endring -> commit-steget hopper over
        return
    now = datetime.now(timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    path = os.path.join(DATA, f"status_{now:%Y-%m-%d}.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        for s in stations:
            w.writerow([stamp, s.get("station_id"),
                        s.get("num_bikes_available"), s.get("num_docks_available"),
                        s.get("is_renting"), s.get("is_returning"),
                        s.get("is_installed"), s.get("last_reported")])
    # oppdater stasjons-metadata (billig, holder navn/koordinater/kapasitet ferske)
    try:
        info = fetch("station_information")
        cols = ["station_id", "name", "lat", "lon", "capacity"]
        with open(os.path.join(DATA, "station_information.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for s in info:
                w.writerow({k: s.get(k) for k in cols})
    except Exception as e:
        print(f"station_information feilet: {e}")
    print(f"{stamp}: {len(stations)} stasjoner logget -> {path}")


if __name__ == "__main__":
    main()
