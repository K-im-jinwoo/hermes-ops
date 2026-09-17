from __future__ import annotations

from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEPLOY_ROOT = PROJECT_ROOT / "deploy"


def test_compose_keeps_candidate_disabled_and_wiki_read_only():
    compose = yaml.safe_load((DEPLOY_ROOT / "compose.yaml").read_text(encoding="utf-8"))
    service = compose["services"]["hermes-gateway"]

    assert "candidate" in service["profiles"]
    assert service["read_only"] is True
    assert not service.get("ports")
    assert any(
        volume["target"] == "/srv/llm-wiki/current" and volume["read_only"] is True
        for volume in service["volumes"]
    )
    assert service["environment"]["HERMES_MEMO_SINK"] == "queue"
    assert service["environment"]["TELEGRAM_BOT_TOKEN_FILE"] == "/run/secrets/telegram-bot-token"
    assert "telegram-bot-token" in service["secrets"]
    assert service["environment"]["GOOGLE_DRIVE_CREDENTIALS_FILE"] == "/run/secrets/google-drive-credentials"
    assert any(
        volume["target"] == "/run/secrets/google-drive-credentials" and volume["read_only"] is True
        for volume in service["volumes"]
    )
    assert compose["networks"]["n8n-private"]["external"] is True


def test_uploader_verifies_before_archiving_and_never_moves_blindly():
    script = (DEPLOY_ROOT / "upload-inbox-queue.sh").read_text(encoding="utf-8")

    assert "--ignore-existing" in script
    assert "rclone check" in script
    assert "--one-way" in script
    assert "mv --" in script
    assert "rclone move" not in script


def test_dockerfile_has_no_runtime_secret_or_host_port():
    content = (DEPLOY_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "TELEGRAM_BOT_TOKEN" not in content
    assert "EXPOSE" not in content
    assert "USER hermes:hermes" in content


def test_deploy_readme_documents_direct_drive_credentials_and_legacy_queue():
    content = (DEPLOY_ROOT / "README.md").read_text(encoding="utf-8")

    assert "GOOGLE_DRIVE_CREDENTIALS_FILE" in content
    assert "client_id" in content
    assert "refresh_token" in content
    assert "rclone" in content
    assert "legacy" in content.lower()
