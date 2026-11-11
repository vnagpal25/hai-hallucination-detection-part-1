"""Export all stored sessions to a flat CSV, one row per trial response.

Reads Firestore using the service account in .streamlit/secrets.toml, or
.local_sessions.json when --local is given.

Usage:
    python export_csv.py                 # -> baseline_responses.csv
    python export_csv.py --local
    python export_csv.py --out my.csv
"""

import argparse
import csv
import json
import tomllib
from pathlib import Path

from storage import COLLECTION, LOCAL_PATH

SESSION_FIELDS = [
    "participant_id", "condition", "status", "started_at", "finished_at",
    "instructions_seconds", "quiz_attempts", "catch_correct", "attention_flag",
    "n_real_trials", "n_real_correct",
]
TRIAL_FIELDS = [
    "position", "trial_id", "is_catch", "gold_label", "answer", "correct",
    "confidence", "seconds",
]


def firestore_sessions():
    from google.cloud import firestore
    from google.oauth2 import service_account

    secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text())
    creds = service_account.Credentials.from_service_account_info(secrets["firestore"])
    client = firestore.Client(credentials=creds, project=creds.project_id)
    return [doc.to_dict() for doc in client.collection(COLLECTION).stream()]


def local_sessions():
    return list(json.loads(LOCAL_PATH.read_text()).values()) if LOCAL_PATH.exists() else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--out", default="baseline_responses.csv")
    args = parser.parse_args()

    sessions = local_sessions() if args.local else firestore_sessions()
    rows = [
        {**{f: s.get(f) for f in SESSION_FIELDS}, **{f: r.get(f) for f in TRIAL_FIELDS}}
        for s in sessions
        for r in s.get("responses", [])
    ]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SESSION_FIELDS + TRIAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    completed = sum(s.get("status") == "completed" for s in sessions)
    print(f"{len(sessions)} sessions ({completed} completed, "
          f"{len(sessions) - completed} terminated), {len(rows)} trial rows -> {args.out}")


if __name__ == "__main__":
    main()
