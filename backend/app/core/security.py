"""口令哈希与访问令牌。

- 口令哈希：stdlib pbkdf2_hmac（原型阶段不引入 bcrypt/argon2 依赖，见 README 已知限制）。
- 令牌：JWT（HS256），密钥来自环境变量 SECRET_KEY。
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings

_PBKDF2_ITERATIONS = 260_000
_ALGO = "pbkdf2_sha256"


def hash_password(raw: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", raw.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_ALGO}${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(raw: str, stored: str) -> bool:
    try:
        algo, iterations_s, salt_hex, digest_hex = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", raw.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations_s)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, role: str) -> tuple[str, int]:
    """返回 (token, 有效秒数)。"""
    settings = get_settings()
    expires_in = settings.token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> dict:
    """解析失败抛 jwt.PyJWTError，由依赖层转换为 401。"""
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
