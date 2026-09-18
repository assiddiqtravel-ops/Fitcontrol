"""Unit tests for Telegram initData validation."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.core.telegram_auth import InitDataError, validate_init_data

BOT_TOKEN = "123456:TEST-TOKEN"


def build_init_data(bot_token: str, *, auth_date: int, user: dict, tamper: bool = False) -> str:
    fields = {
        "auth_date": str(auth_date),
        "query_id": "AAE",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if tamper:
        digest = "0" * len(digest)
    fields["hash"] = digest
    return urlencode(fields)


def test_valid_init_data():
    now = int(time.time())
    user = {"id": 42, "first_name": "Ali", "username": "ali"}
    init = build_init_data(BOT_TOKEN, auth_date=now, user=user)
    parsed = validate_init_data(init, BOT_TOKEN, max_age_seconds=3600, now=now)
    assert parsed.user.id == 42
    assert parsed.user.username == "ali"
    assert parsed.auth_date == now


def test_bad_signature():
    now = int(time.time())
    user = {"id": 42, "first_name": "Ali"}
    init = build_init_data(BOT_TOKEN, auth_date=now, user=user, tamper=True)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(init, BOT_TOKEN, max_age_seconds=3600, now=now)
    assert exc.value.code == "bad_signature"


def test_wrong_token_fails():
    now = int(time.time())
    user = {"id": 42, "first_name": "Ali"}
    init = build_init_data(BOT_TOKEN, auth_date=now, user=user)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(init, "different-token", max_age_seconds=3600, now=now)
    assert exc.value.code == "bad_signature"


def test_expired_init_data():
    issued = int(time.time()) - 10_000
    user = {"id": 42, "first_name": "Ali"}
    init = build_init_data(BOT_TOKEN, auth_date=issued, user=user)
    with pytest.raises(InitDataError) as exc:
        validate_init_data(init, BOT_TOKEN, max_age_seconds=3600, now=issued + 10_000)
    assert exc.value.code == "expired"


def test_missing_hash():
    init = urlencode({"auth_date": str(int(time.time())), "user": "{}"})
    with pytest.raises(InitDataError) as exc:
        validate_init_data(init, BOT_TOKEN)
    assert exc.value.code == "missing_hash"


def test_tampered_field_after_signing_detected():
    """Changing the user id after signing must invalidate the signature."""
    now = int(time.time())
    user = {"id": 42, "first_name": "Ali"}
    init = build_init_data(BOT_TOKEN, auth_date=now, user=user)
    # Attacker swaps in a different user id but keeps the original hash.
    forged = init.replace("%2242%22", "%2299%22").replace('"id":42', '"id":99')
    forged = forged.replace("42", "99", 1)
    with pytest.raises(InitDataError):
        validate_init_data(forged, BOT_TOKEN, max_age_seconds=3600, now=now)
