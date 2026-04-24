import json
import os
from datetime import datetime, timezone


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_PATH = os.path.join(DATA_DIR, "admin_control.json")

DEFAULT_STATE = {
    "active_admin": {
        "email": "alihydershar688@gmail.com",
        "admin_id": "A2024001",
    },
    "authorized_admins": [
        {
            "email": "alihydershar688@gmail.com",
            "admin_id": "A2024001",
        }
    ],
    "transfer_log": []
}


def _normalize(value):
    return (value or "").strip().lower()


def _ensure_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_PATH):
        save_admin_control(DEFAULT_STATE)


def load_admin_control():
    _ensure_storage()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return json.loads(json.dumps(DEFAULT_STATE))


def save_admin_control(state):
    _ensure_storage()
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def is_authorized_admin(state, email=None, admin_id=None):
    email_n = _normalize(email)
    admin_id_n = _normalize(admin_id)
    active = state.get("active_admin") or {}
    if email_n and _normalize(active.get("email")) == email_n:
        return True
    if admin_id_n and _normalize(active.get("admin_id")) == admin_id_n:
        return True
    for admin in state.get("authorized_admins", []):
        if email_n and _normalize(admin.get("email")) == email_n:
            return True
        if admin_id_n and _normalize(admin.get("admin_id")) == admin_id_n:
            return True
    return False


def is_active_admin(state, email=None, admin_id=None):
    active = state.get("active_admin") or {}
    email_n = _normalize(email)
    admin_id_n = _normalize(admin_id)
    return (
        (email_n and _normalize(active.get("email")) == email_n)
        or (admin_id_n and _normalize(active.get("admin_id")) == admin_id_n)
    )


def public_summary(state):
    active = state.get("active_admin") or {}
    return {
        "active_admin": {
            "email": active.get("email"),
            "admin_id": active.get("admin_id"),
        },
        "authorized_count": len(state.get("authorized_admins", [])),
        "transfer_log": state.get("transfer_log", [])[-10:]
    }


def record_transfer(state, actor_email, previous_admin, next_admin):
    state.setdefault("transfer_log", []).append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_email": actor_email,
        "previous_admin": previous_admin,
        "next_admin": next_admin,
    })
    state["transfer_log"] = state["transfer_log"][-50:]
    return state
