#!/usr/bin/env python3
"""
Oslo Bysykkel — GBFS status-logger, SELVLOOPENDE for GitHub Actions.

Bakgrunn: GitHub struper planlagte (cron) workflows, så en '*/15'-cron fyrer i
praksis bare hver 3.-4. time. Løsningen: EN kjøring poller selv i en løkke med
sleep i opptil ~6 timer (GitHubs maks jobblengde), og committer underveis.
En cron hver 6. time starter en ny kjøring, så du dekker døgnet med 15-min-oppløsning.

Skriver samme format som før: bysykkel_status/status_YYYY-MM-DD.csv
Kun standardbibliotek for selve pollingen; git via subprocess for commit/push.
"""
import csv, json, os, subprocess, time, urllib.request
from datetime import datetime, timezone

# ---------------- Konfig (kan overstyres via env i workflowen) ----------------
BASE          = "https://gbfs.urbansharing.com/oslobysykkel.no"
CLIENT_ID     = os.environ.get("CLIENT_ID", "syver-stave-dtu-bachelor")
POLL_MINUTES  = int(os.environ.get("POLL_MINUTES", "15"))    # hvor ofte vi poller
RUN_MINUTES   = int(os.environ.get("RUN_MINUTES", "340"))    # hvor lenge én kjøring varer (<360!)
COMMIT_MINUTES= int(os.environ.get("COMMIT_MINUTES", "60"))  # hvor ofte vi committer/pusher
OUT_DIR       = os.environ.get("OUT_DIR", "bysykkel_status")
# -----------------------------------------------------------------------------

HEADERS = {"Client-Identifier": CLIENT_ID, "User-Agent": f"{CLIENT_ID} (bachelorprosjekt)"}
COLS = ["polled_at_utc", "station_id", "num_bikes_available", "num_docks_available",
        "is_renting", "is_returning", "is_installed", "last_reported"]


def fetch(feed):
    req = urllib.request.Request(f"{BASE}/{feed}.json", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["data"]["stations"]


def append_snapshot():
    """Poll én gang og legg til en rad per stasjon i dagens CSV. Returner antall rader."""
    now = datetime.now(timezone.utc)
    path = os.path.join(OUT_DIR, f"status_{now.strftime('%Y-%m-%d')}.csv")
    new = not os.path.exists(path)
    stations = fetch("station_status")
    stamp = now.isoformat(timespec="seconds")
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLS)
        for s in stations:
            w.writerow([stamp, s.get("station_id"),
                        s.get("num_bikes_available"), s.get("num_docks_available"),
                        s.get("is_renting"), s.get("is_returning"),
                        s.get("is_installed"), s.get("last_reported")])
    return len(stations)


def git(*args):
    return subprocess.run(["git", *args], cwd=".", capture_output=True, text=True)


def commit_push():
    git("config", "user.name", "logger-bot")
    git("config", "user.email", "logger@users.noreply.github.com")
    git("add", OUT_DIR)
    r = git("commit", "-m", f"status {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    if "nothing to commit" in (r.stdout + r.stderr):
        return
    git("pull", "--rebase", "--autostash")     # unngå konflikt med forrige kjøring
    p = git("push")
    print("  commit+push:", "ok" if p.returncode == 0 else p.stderr.strip()[:200])


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # metadata (navn/koordinater/kapasitet) én gang hvis den mangler
    meta = os.path.join(OUT_DIR, "station_information.csv")
    if not os.path.exists(meta):
        try:
            st = fetch("station_information")
            with open(meta, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=["station_id", "name", "lat", "lon", "capacity"],
                                   extrasaction="ignore")
                w.writeheader()
                for s in st:
                    w.writerow({k: s.get(k) for k in ["station_id", "name", "lat", "lon", "capacity"]})
            print(f"  lagret {meta} ({len(st)} stasjoner)")
        except Exception as e:
            print(f"  [advarsel] station_information: {e}")

    end = time.time() + RUN_MINUTES * 60
    last_commit = time.time()
    print(f"Selvloopende logger: poller hvert {POLL_MINUTES} min i {RUN_MINUTES} min "
          f"(commit hvert {COMMIT_MINUTES} min).")
    while time.time() < end:
        t0 = time.time()
        try:
            n = append_snapshot()
            print(f"  {datetime.now(timezone.utc).isoformat(timespec='seconds')}  {n} stasjoner")
        except Exception as e:
            print(f"  [advarsel] poll feilet: {e}")
        if time.time() - last_commit >= COMMIT_MINUTES * 60:
            commit_push(); last_commit = time.time()
        # sov resten av intervallet, men aldri forbi slutt-tiden
        time.sleep(max(1, min(POLL_MINUTES * 60 - (time.time() - t0), end - time.time())))
    commit_push()   # siste commit før jobben avsluttes
    print("Kjøring ferdig.")


if __name__ == "__main__":
    main()
