# Oracle deployment

This deployment gives Hermes a direct Google Drive CRUD tool while keeping the
OAuth credential file outside the image and repository.

## Runtime boundary

- `hermes-gateway` reads the synchronized WIKI at `/srv/llm-wiki/current`.
- Approved memos are created directly in the configured Google Drive Inbox.
- Duplicate content is skipped; a matching title with different content is
  returned for review. Drive failures never produce a saved acknowledgement.
- Explicit Google Drive natural-language requests use the Drive v3 REST API
  directly from Hermes.
- Natural-language WIKI questions call the existing authenticated
  `wiki-agent:8080/ask` service using the Telegram chat ID for continuity.
  Telegram users do not need an `/ask` command.
- The existing `rclone` queue uploader remains a legacy fallback and is not
  used by the candidate Compose service.
- `GOOGLE_DRIVE_CREDENTIALS_FILE` is mounted read-only at runtime and is never
  copied into the image.
- The `candidate` Compose profile is intentionally disabled by default.
- `TELEGRAM_DELETE_WEBHOOK` stays `false` while n8n is still the active
  Telegram receiver.

## Host paths

Create these paths on Oracle and make them writable by the runtime UID:

```text
/opt/hermes-ops
/srv/hermes-ops/state
/srv/hermes-ops/queue/pending
/srv/hermes-ops/queue/uploaded
/srv/hermes-ops/telegram-bot-token
/srv/hermes-ops/google-drive-credentials.json
/srv/llm-wiki/wiki-agent-shared-secret
/srv/hermes-ops/uploader.env
```

On the current Oracle host, `ubuntu` is UID/GID `1001:1001`; set
`HERMES_CONTAINER_UID=1001` and `HERMES_CONTAINER_GID=1001` in the Compose
environment. The bot token file must be mode `0600` and must not be committed. The
Google Drive credential file must also be mode `0600`, must not be committed,
and must be readable by the Hermes container UID. Its minimum shape is:

```json
{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

Set the host path and the **exact `wiki/00_Inbox` folder ID** in the deployment
environment:

```text
GOOGLE_DRIVE_CREDENTIALS_HOST_FILE=/srv/hermes-ops/google-drive-credentials.json
GOOGLE_DRIVE_ROOT_ID=<wiki/00_Inbox folder ID>
```

The direct memo sink refuses to save when this ID is missing. It scans existing
Markdown Inbox notes before creating a new draft and fails closed when the
listing reaches 1000 files; this limit needs pagination before a larger Inbox
can be used.

The existing wiki-agent shared key is mounted read-only as
`/run/secrets/wiki-agent-key`. The candidate container must be able to read
the host file; do not copy the key into the image or repository. Keep Hermes
and wiki-agent on the private `n8n-infra_default` Docker network.

The `uploader.env` file is only for the legacy queue fallback and may contain:

```text
HERMES_INBOX_QUEUE_DIR=/srv/hermes-ops/queue
HERMES_INBOX_REMOTE=wiki-drive:WIKI/wiki/00_Inbox
HERMES_INBOX_LOCK_FILE=/var/lock/hermes-inbox-uploader.lock
```

## Direct Google Drive CRUD candidate validation

Provision the existing Google account's OAuth credential file with the
required Drive write permission. Validate the candidate configuration and
one-off container before starting Telegram polling:

```bash
docker compose --env-file deploy/candidate.env -f deploy/compose.yaml --profile candidate config --quiet
docker compose --env-file deploy/candidate.env -f deploy/compose.yaml --profile candidate run --rm --no-deps --entrypoint python hermes-gateway -c 'import telegram_gateway as g; assert g._load_env_token(); assert g._load_allowed_user_ids(); print("ready")'
```

Check the bot's current webhook before polling. Long polling and an active
webhook cannot receive updates simultaneously. When Telegram is routed to
Hermes, test a WIKI question, a unique file, and one approved memo in the
configured Inbox:

```text
최근 운동 기록은?
구글드라이브에서 파일 목록 찾아줘
구글드라이브에 파일명: hermes-crud-smoke.md 내용: smoke create 저장해줘
구글드라이브 파일명: hermes-crud-smoke.md 내용: smoke update 수정해줘
구글드라이브 파일명: hermes-crud-smoke.md 삭제해줘
이 메모를 WIKI에 기록해줘
승인 <미리보기의 승인 ID>
```

Confirm each operation in Drive and verify that the memo was created only
after the approval reply. Do not remove n8n until its remaining routes have
been inventoried and the Telegram cutover has a rollback path. The separate
Codex and Antigravity CLI routes in this repository still rely on local
Windows executables and are not validated in the Oracle image.

## Queue uploader

Install `hermes-inbox-uploader.service` and its timer only after the separate
write remote has passed a controlled upload test. The uploader copies and
checks a snapshot of pending files before archiving them; failed uploads stay
in `pending` for retry.
