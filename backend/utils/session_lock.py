import json
import os
from datetime import datetime, timedelta, timezone


DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_PATH = os.path.join(DATA_DIR, "session_locks.json")


def _env_float(name, default):
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except Exception:
        return float(default)


DEFAULT_TTL_MINUTES = max(0.5, _env_float("SESSION_LOCK_TTL_MINUTES", 2))


def _normalize(value):
    return (value or "").strip().lower()


def _utc_now():
    return datetime.now(timezone.utc)


def _ensure_storage():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(STATE_PATH):
        with open(STATE_PATH, "w", encoding="utf-8") as fh:
            json.dump({}, fh, indent=2)


def load_session_locks():
    _ensure_storage()
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_session_locks(state):
    _ensure_storage()
    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def _expiry_iso(ttl_minutes=DEFAULT_TTL_MINUTES):
    return (_utc_now() + timedelta(minutes=ttl_minutes)).isoformat()


def _is_expired(lock):
    try:
        expires_at = datetime.fromisoformat(lock.get("expires_at"))
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= _utc_now()
    except Exception:
        return True


def _lock_key(email, role):
    return f"{_normalize(role)}:{_normalize(email)}"


def _build_lock(email, role, device_id, ttl_minutes=DEFAULT_TTL_MINUTES):
    now = _utc_now().isoformat()
    return {
        "email": _normalize(email),
        "role": _normalize(role),
        "device_id": (device_id or "").strip(),
        "expires_at": _expiry_iso(ttl_minutes),
        "updated_at": now,
        "created_at": now,
    }


def _purge_expired(state):
    stale_keys = [
        key for key, value in (state or {}).items()
        if not isinstance(value, dict) or _is_expired(value)
    ]
    for key in stale_keys:
        state.pop(key, None)
    return state


def acquire_session_lock(state, email, role, device_id, ttl_minutes=DEFAULT_TTL_MINUTES, force_takeover=False):
    email_n = _normalize(email)
    role_n = _normalize(role)
    device_n = (device_id or "").strip()

    if role_n not in ("teacher", "admin"):
        return True, None, None
    if not email_n or not device_n:
        return False, "email and device_id are required", None

    _purge_expired(state)
    key = _lock_key(email_n, role_n)
    existing = state.get(key)
    if existing and existing.get("device_id") != device_n:
        if not force_takeover:
            return False, "This account is already active on another device.", existing
        previous = dict(existing)
    else:
        previous = None

    lock = _build_lock(email_n, role_n, device_n, ttl_minutes)
    if existing and existing.get("created_at"):
        lock["created_at"] = existing.get("created_at")
    if previous:
        lock["previous_device_id"] = previous.get("device_id")
        lock["taken_over_at"] = _utc_now().isoformat()
    state[key] = lock
    return True, None, lock


def renew_session_lock(state, email, role, device_id, ttl_minutes=DEFAULT_TTL_MINUTES):
    email_n = _normalize(email)
    role_n = _normalize(role)
    device_n = (device_id or "").strip()

    if role_n not in ("teacher", "admin"):
        return True, None, None
    if not email_n or not device_n:
        return False, "email and device_id are required", None

    _purge_expired(state)
    key = _lock_key(email_n, role_n)
    existing = state.get(key)
    if existing and existing.get("device_id") != device_n:
        return False, "This account is already active on another device.", existing

    if not existing:
        return acquire_session_lock(state, email_n, role_n, device_n, ttl_minutes)

    renewed = dict(existing)
    renewed["expires_at"] = _expiry_iso(ttl_minutes)
    renewed["updated_at"] = _utc_now().isoformat()
    state[key] = renewed
    return True, None, renewed


def release_session_lock(state, email, role, device_id):
    email_n = _normalize(email)
    role_n = _normalize(role)
    device_n = (device_id or "").strip()

    if role_n not in ("teacher", "admin"):
        return True
    if not email_n or not device_n:
        return False

    _purge_expired(state)
    key = _lock_key(email_n, role_n)
    existing = state.get(key)
    if not existing:
        return True
    if existing.get("device_id") != device_n:
        return False
    state.pop(key, None)
    return True
