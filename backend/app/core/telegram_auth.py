"""Telegram Mini App ``initData`` validation.

Implements the official verification algorithm:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

Steps:
1. Parse the ``initData`` query string into key/value pairs.
2. Remove ``hash`` (and the optional ``signature`` field, which is part of the
   newer Ed25519 scheme and is not part of the HMAC data-check-string).
3. Build a ``data_check_string``: ``key=value`` pairs sorted by key, joined
   with ``\n``.
4. secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
5. computed_hash = HMAC_SHA256(key=secret_key, msg=data_check_string)
6. Compare (constant time) with the provided ``hash``.
7. Enforce freshness via ``auth_date``.

We NEVER log the raw initData or the bot token.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl


class InitDataError(Exception):
    """Raised when initData is missing, malformed, has a bad signature, or is stale."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None
    is_premium: bool = False


@dataclass(frozen=True)
class InitData:
    user: TelegramUser
    auth_date: int
    raw_user: dict
    start_param: str | None = None


def _build_data_check_string(pairs: list[tuple[str, str]]) -> str:
    filtered = [(k, v) for k, v in pairs if k not in ("hash", "signature")]
    filtered.sort(key=lambda kv: kv[0])
    return "\n".join(f"{k}={v}" for k, v in filtered)


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int | None = 86400,
    now: int | None = None,
) -> InitData:
    """Validate a Telegram Mini App initData string.

    Raises :class:`InitDataError` on any failure. Returns parsed :class:`InitData`
    on success.
    """
    if not init_data:
        raise InitDataError("missing_init_data", "initData is empty")
    if not bot_token:
        raise InitDataError("server_misconfigured", "Bot token is not configured")

    # keep_blank_values so an empty field does not silently vanish from the check
    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data = dict(pairs)

    provided_hash = data.get("hash")
    if not provided_hash:
        raise InitDataError("missing_hash", "initData has no hash field")

    data_check_string = _build_data_check_string(pairs)

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(computed_hash, provided_hash):
        raise InitDataError("bad_signature", "initData signature mismatch")

    # Freshness
    auth_date_raw = data.get("auth_date")
    if not auth_date_raw:
        raise InitDataError("missing_auth_date", "initData has no auth_date")
    try:
        auth_date = int(auth_date_raw)
    except ValueError as exc:  # pragma: no cover - defensive
        raise InitDataError("bad_auth_date", "auth_date is not an integer") from exc

    current = int(time.time()) if now is None else now
    if max_age_seconds is not None and (current - auth_date) > max_age_seconds:
        raise InitDataError("expired", "initData is too old")
    # Reject clearly future-dated tokens (clock skew tolerance: 5 minutes)
    if auth_date - current > 300:
        raise InitDataError("bad_auth_date", "auth_date is in the future")

    user_raw = data.get("user")
    if not user_raw:
        raise InitDataError("missing_user", "initData has no user field")
    try:
        user_dict = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise InitDataError("bad_user", "user field is not valid JSON") from exc

    if "id" not in user_dict:
        raise InitDataError("bad_user", "user field has no id")

    user = TelegramUser(
        id=int(user_dict["id"]),
        first_name=user_dict.get("first_name"),
        last_name=user_dict.get("last_name"),
        username=user_dict.get("username"),
        language_code=user_dict.get("language_code"),
        is_premium=bool(user_dict.get("is_premium", False)),
    )

    return InitData(
        user=user,
        auth_date=auth_date,
        raw_user=user_dict,
        start_param=data.get("start_param"),
    )
