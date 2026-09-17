from __future__ import annotations

import telegram_gateway


def test_allowed_user_ids_are_parsed_as_a_positive_integer_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123456789, 987654321")

    assert telegram_gateway._load_allowed_user_ids() == frozenset({123456789, 987654321})


def test_invalid_allowlist_fails_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", "123456789,not-an-id")

    assert telegram_gateway._load_allowed_user_ids() == frozenset()


def test_missing_allowlist_fails_closed(monkeypatch):
    monkeypatch.setattr(telegram_gateway, "_load_env_file_value", lambda name: None)

    assert telegram_gateway._load_allowed_user_ids() == frozenset()


def test_only_an_allowed_telegram_sender_can_be_processed():
    allowed_message = {"from": {"id": 123456789}}
    blocked_message = {"from": {"id": 111111111}}

    assert telegram_gateway._is_allowed_telegram_user(allowed_message, frozenset({123456789}))
    assert not telegram_gateway._is_allowed_telegram_user(blocked_message, frozenset({123456789}))
    assert not telegram_gateway._is_allowed_telegram_user({}, frozenset({123456789}))


def test_webhook_deletion_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(telegram_gateway, "_load_env_file_value", lambda name: None)

    assert telegram_gateway._should_delete_webhook() is False


def test_webhook_deletion_requires_explicit_true_setting(monkeypatch):
    monkeypatch.setattr(
        telegram_gateway,
        "_load_env_file_value",
        lambda name: "true" if name == "TELEGRAM_DELETE_WEBHOOK" else None,
    )

    assert telegram_gateway._should_delete_webhook() is True
