from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet():
    key = settings.FERNET_KEY
    if isinstance(key, str):
        key = key.encode('utf-8')
    return Fernet(key)


def encrypt_secret(plaintext):
    if plaintext is None or plaintext == '':
        return ''
    return _fernet().encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_secret(ciphertext):
    if not ciphertext:
        return ''
    try:
        return _fernet().decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError):
        return ''
