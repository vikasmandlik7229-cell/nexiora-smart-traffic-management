"""Local authentication, replacing Firebase Authentication: password hashing
(stdlib PBKDF2-HMAC-SHA256, no extra dependency) and JWT issuing/verifying
(pyjwt, the one new dependency this migration needs).

Users live in the same generic `documents` table as everything else
(collection="users", doc id = email - simpler than Firebase's opaque uid,
since nothing else depends on uids being random).
"""
import hashlib
import secrets
import time

import jwt

import config

_PBKDF2_ITERATIONS = 260_000


def hash_password(password: str, salt: str = None) -> dict:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS).hex()
    return {"salt": salt, "passwordHash": digest}


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERATIONS).hex()
    return secrets.compare_digest(candidate, expected_hash)


def issue_token(email: str, role: str, vehicle_id: str = None) -> str:
    payload = {
        "sub": email,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + config.JWT_EXPIRY_HOURS * 3600,
    }
    if vehicle_id:
        # Lets the backend target an alert at "the driver logged in as
        # vehicle X" (accidents/manager.py's nearest-ambulance dispatch)
        # without a per-request database lookup of the user's own record.
        payload["vehicleId"] = vehicle_id
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def verify_token(token: str) -> dict:
    """Raises jwt.PyJWTError on an invalid/expired token - callers catch it."""
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
