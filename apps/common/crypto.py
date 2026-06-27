import base64
import hashlib

from django.conf import settings
from cryptography.fernet import Fernet


def normalize_key(raw_key):
    if not raw_key:
        return None
    key = str(raw_key).strip().encode()
    missing_padding = len(key) % 4
    if missing_padding:
        key += b'=' * (4 - missing_padding)
    try:
        base64.urlsafe_b64decode(key)
    except Exception:
        return None
    return key


def dev_fallback_key():
    secret = getattr(settings, 'SECRET_KEY', '')
    if not secret:
        return None
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())


def candidate_fernets(include_expired=False):
    raw_keys = [getattr(settings, 'FERNET_KEY', '')]
    if include_expired:
        raw_keys.extend(getattr(settings, 'PREVIOUS_FERNET_KEYS', []))
    for raw_key in raw_keys:
        key = normalize_key(raw_key)
        if key:
            yield Fernet(key)
    dev_key = dev_fallback_key()
    if dev_key:
        yield Fernet(dev_key)


def get_fernet():
    key = normalize_key(getattr(settings, 'FERNET_KEY', ''))
    if not key:
        raise ValueError("FERNET_KEY is not set or invalid in settings")
    return Fernet(key)
