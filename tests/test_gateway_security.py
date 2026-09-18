from __future__ import annotations

import urllib.error

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


def test_successful_poll_refreshes_heartbeat(monkeypatch, tmp_path):
    heartbeat = tmp_path / "heartbeat"

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"ok": true, "result": []}'

    monkeypatch.setenv("HERMES_HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.setattr(telegram_gateway.urllib.request, "urlopen", lambda *args, **kwargs: Response())

    assert telegram_gateway.fetch_telegram_updates("test-token", None, timeout_seconds=1) == []
    assert heartbeat.is_file()


def test_failed_poll_does_not_create_heartbeat(monkeypatch, tmp_path):
    heartbeat = tmp_path / "heartbeat"

    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")

    monkeypatch.setenv("HERMES_HEARTBEAT_PATH", str(heartbeat))
    monkeypatch.setattr(telegram_gateway.urllib.request, "urlopen", fail)
    monkeypatch.setattr(telegram_gateway.time, "sleep", lambda *_: None)

    assert telegram_gateway.fetch_telegram_updates("test-token", None, timeout_seconds=1) == []
    assert not heartbeat.exists()


def test_env_file_value_can_be_loaded_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "secret"
    secret_file.write_text("secret-value\n", encoding="utf-8")
    monkeypatch.delenv("TEST_SECRET", raising=False)
    monkeypatch.setenv("TEST_SECRET_FILE", str(secret_file))

    assert telegram_gateway._load_env_file_value("TEST_SECRET") == "secret-value"


def test_polling_logs_do_not_include_personal_message_content(monkeypatch, capsys):
    private_prompt = "비밀 메모를 WIKI에서 찾아줘"
    private_answer = "민감한 개인 답변"
    fetch_count = 0

    def fetch_once(*args, **kwargs):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count > 1:
            raise KeyboardInterrupt
        return [{
            "update_id": 1,
            "message": {
                "from": {"id": 123, "first_name": "Private Name"},
                "chat": {"id": 456},
                "text": private_prompt,
            },
        }]

    monkeypatch.setattr(telegram_gateway, "_load_env_token", lambda: "test-token")
    monkeypatch.setattr(telegram_gateway, "_load_allowed_user_ids", lambda: frozenset({123}))
    monkeypatch.setattr(telegram_gateway, "_should_delete_webhook", lambda: False)
    monkeypatch.setattr(telegram_gateway, "fetch_telegram_updates", fetch_once)
    monkeypatch.setattr(telegram_gateway, "process_user_prompt", lambda *args, **kwargs: private_answer)
    monkeypatch.setattr(telegram_gateway, "send_telegram_message", lambda *args, **kwargs: True)

    telegram_gateway.start_gateway_polling()

    output = capsys.readouterr().out
    assert private_prompt not in output
    assert private_answer not in output
    assert "Private Name" not in output
    assert "[전송] 성공" in output


def test_polling_reports_rejected_sender_without_identity(monkeypatch, capsys):
    fetch_count = 0

    def fetch_once(*args, **kwargs):
        nonlocal fetch_count
        fetch_count += 1
        if fetch_count > 1:
            raise KeyboardInterrupt
        return [{"update_id": 1, "message": {
            "from": {"id": 999, "first_name": "Private Name"},
            "chat": {"id": 456}, "text": "Private message",
        }}]

    monkeypatch.setattr(telegram_gateway, "_load_env_token", lambda: "test-token")
    monkeypatch.setattr(telegram_gateway, "_load_allowed_user_ids", lambda: frozenset({123}))
    monkeypatch.setattr(telegram_gateway, "_should_delete_webhook", lambda: False)
    monkeypatch.setattr(telegram_gateway, "fetch_telegram_updates", fetch_once)
    monkeypatch.setattr(telegram_gateway, "process_user_prompt", lambda *args, **kwargs: None)
    telegram_gateway.start_gateway_polling()

    output = capsys.readouterr().out
    assert "[거부] 허용되지 않은 발신자" in output
    assert "999" not in output
    assert "Private Name" not in output
    assert "Private message" not in output
