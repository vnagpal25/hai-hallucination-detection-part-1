"""Export all stored sessions to a flat CSV, one row per trial response.

Reads Firestore using the service account in .streamlit/secrets.toml, or
.local_sessions.json when --local is given.

Usage:
    python export_csv.py                    # baseline -> baseline_responses.csv
    python export_csv.py --condition ai     # AI condition -> ai_responses.csv
    python export_csv.py --local            # read the dev-mode local file instead
    python export_csv.py --out my.csv
"""

import argparse
import csv
import json
import tomllib
from pathlib import Path

import study
from storage import COLLECTION, local_path

SESSION_FIELDS = [
    "participant_id", "condition", "status", "started_at", "finished_at",
    "instructions_seconds", "quiz_attempts", "catch_correct", "attention_flag",
    "n_real_trials", "n_real_correct",
]
TRIAL_FIELDS = [
    "position", "trial_id", "is_catch", "gold_label", "answer", "correct",
    "confidence", "seconds",
]
# extra columns for the AI condition
AI_SESSION_FIELDS = [
    "n_real_initial_correct", "n_ai_correct", "n_switched",
] + [f"survey_{item['key']}" for item in study.SURVEY]
AI_TRIAL_FIELDS = [
    "ai_verdict", "ai_correct", "ai_flagged_span",
    "initial_answer", "initial_correct", "initial_confidence", "initial_seconds",
    "final_answer", "final_confidence", "final_seconds",
    "agree_initial", "agree_final", "switched", "switched_to_ai",
    "over_reliance", "under_reliance",
]
CONDITIONS = {"baseline": COLLECTION, "ai": study.AI_COLLECTION}


def firestore_sessions(collection):
    from google.cloud import firestore
    from google.oauth2 import service_account

    secrets = tomllib.loads(Path(".streamlit/secrets.toml").read_text())
    creds = service_account.Credentials.from_service_account_info(secrets["firestore"])
    client = firestore.Client(credentials=creds, project=creds.project_id)
    return [doc.to_dict() for doc in client.collection(collection).stream()]


def local_sessions(collection):
    path = local_path(collection)
    return list(json.loads(path.read_text()).values()) if path.exists() else []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", choices=CONDITIONS, default="baseline")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--out")
    args = parser.parse_args()
    out = args.out or f"{args.condition}_responses.csv"
    collection = CONDITIONS[args.condition]

    session_fields, trial_fields = SESSION_FIELDS, TRIAL_FIELDS
    if args.condition == "ai":
        session_fields = SESSION_FIELDS + AI_SESSION_FIELDS
        trial_fields = TRIAL_FIELDS + AI_TRIAL_FIELDS

    sessions = local_sessions(collection) if args.local else firestore_sessions(collection)
    rows = []
    for s in sessions:
        flat = {**s, **{f"survey_{k}": v for k, v in (s.get("survey") or {}).items()}}
        for r in s.get("responses", []):
            rows.append(
                {**{f: flat.get(f) for f in session_fields},
                 **{f: r.get(f) for f in trial_fields}}
            )
    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=session_fields + trial_fields)
        writer.writeheader()
        writer.writerows(rows)

    completed = sum(s.get("status") == "completed" for s in sessions)
    print(f"{len(sessions)} sessions ({completed} completed, "
          f"{len(sessions) - completed} terminated), {len(rows)} trial rows -> {out}")


if __name__ == "__main__":
    main()
