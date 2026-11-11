"""Session storage, backed by Cloud Firestore.

If no [firestore] credentials are configured (local development), sessions are
written to .local_sessions.json instead and the app shows a warning banner.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

COLLECTION = "baseline_sessions"  # default; the AI condition passes "ai_sessions"
LOCAL_PATH = Path(__file__).parent / ".local_sessions.json"


def local_path(collection=COLLECTION):
    if collection == COLLECTION:
        return LOCAL_PATH
    return Path(__file__).parent / f".local_{collection}.json"


def using_firestore():
    try:
        return "firestore" in st.secrets
    except Exception:  # no secrets.toml at all
        return False


@st.cache_resource
def _client():
    from google.cloud import firestore
    from google.oauth2 import service_account

    # service account key lives in .streamlit/secrets.toml, never in the repo
    creds = service_account.Credentials.from_service_account_info(
        dict(st.secrets["firestore"])
    )
    return firestore.Client(credentials=creds, project=creds.project_id)


def _read_local(collection=COLLECTION):
    path = local_path(collection)
    return json.loads(path.read_text()) if path.exists() else {}


def save(code, session, collection=COLLECTION):
    """Store one participant's session in a document named after their code."""
    doc = {**session, "code": code, "saved_at": datetime.now(timezone.utc)}
    if using_firestore():
        _client().collection(collection).document(code).set(doc)
    else:
        data = _read_local(collection)
        data[code] = doc
        local_path(collection).write_text(json.dumps(data, indent=2, default=str))


def load(code, collection=COLLECTION):
    """Return the stored session for a code, or None if it doesn't exist."""
    if using_firestore():
        doc = _client().collection(collection).document(code).get()
        return doc.to_dict() if doc.exists else None
    return _read_local(collection).get(code)
