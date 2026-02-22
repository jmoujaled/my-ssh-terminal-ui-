import hmac
import time

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from config import settings

SALT = "ssh-terminal-session"


def check_password(provided: str) -> bool:
    """
    Constant-time comparison of the provided password against the admin password.
    Returns False if auth is not enabled (no admin password set).
    """
    expected = settings.admin_password
    if not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def create_session(secret_key: str, timeout_minutes: int) -> str:
    """
    Create a signed session token with an embedded timestamp.
    The token is URL-safe and tamper-proof.
    """
    s = URLSafeTimedSerializer(secret_key)
    return s.dumps({"created": time.time()}, salt=SALT)


def verify_session(token: str, secret_key: str, max_age_seconds: int = 1800) -> bool:
    """
    Verify a session token's signature and check it hasn't expired.
    Returns True if valid, False if tampered, expired, or malformed.
    """
    s = URLSafeTimedSerializer(secret_key)
    try:
        s.loads(token, salt=SALT, max_age=max_age_seconds)
        return True
    except (BadSignature, SignatureExpired):
        return False
