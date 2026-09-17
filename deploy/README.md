# Oracle deployment

This deployment gives Hermes a direct Google Drive CRUD tool while keeping the
OAuth credential file outside the image and repository.

## Runtime boundary

- `hermes-gateway` reads the synchronized WIKI at `/srv/llm-wiki/current`.
- Approved memos are written to `/srv/hermes-ops/queue/pending` only.
- Explicit Google Drive natural-language requests use the Drive v3 REST API
  directly from Hermes.
- The existing `rclone` queue uploader is a legacy fallback for approved WIKI
  memos; it is not the Hermes CRUD interface.
- `GOOGLE_DRIVE_CREDENTIALS_FILE` is mounted read-only at runtime and is never
  copied into the image.
- The `candidate` Compose profile is intentionally disabled by default.
- `TELEGRAM_DELETE_WEBHOOK` stays `false` while n8n is still the active
  Telegram receiver.

## Host paths

Create these paths on Oracle and make them writable by the `ubuntu` user and
the runtime UID configured in `compose.yaml`:

```text
/opt/hermes-ops
/srv/hermes-ops/state
/srv/hermes-ops/queue/pending
/srv/hermes-ops/queue/uploaded
/srv/hermes-ops/telegram-bot-token
/srv/hermes-ops/google-drive-credentials.json
/srv/hermes-ops/uploader.env
```

The bot token file must be mode `0600` and must not be committed. The
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

Set the host path and optional default parent folder in the deployment
environment:

```text
GOOGLE_DRIVE_CREDENTIALS_HOST_FILE=/srv/hermes-ops/google-drive-credentials.json
GOOGLE_DRIVE_ROOT_ID=<WIKI 또는 00_Inbox 폴더 ID>
```

The `uploader.env` file is only for the legacy queue fallback and may contain:

```text
HERMES_INBOX_QUEUE_DIR=/srv/hermes-ops/queue
HERMES_INBOX_REMOTE=wiki-drive:WIKI/wiki/00_Inbox
HERMES_INBOX_LOCK_FILE=/var/lock/hermes-inbox-uploader.lock
```

## Direct Google Drive CRUD candidate validation

Provision the existing Google account's OAuth credential file with the
required Drive write permission, then run the candidate while n8n still owns
the Telegram webhook:

```bash
chmod 600 /srv/hermes-ops/google-drive-credentials.json
docker compose --profile candidate build hermes-gateway
docker compose --profile candidate up -d hermes-gateway
docker compose logs --tail=100 hermes-gateway
```

From Telegram, test a unique file in the configured parent folder:

```text
구글드라이브에서 파일 목록 찾아줘
구글드라이브에 파일명: hermes-crud-smoke.md 내용: smoke create 저장해줘
구글드라이브 파일명: hermes-crud-smoke.md 내용: smoke update 수정해줘
구글드라이브 파일명: hermes-crud-smoke.md 삭제해줘
```

Confirm each operation in Drive before considering the tool live. Do not set
`TELEGRAM_DELETE_WEBHOOK=true` until this candidate path and the existing WIKI
read path have both been verified.

## Candidate validation

Build and start Hermes only as a candidate while n8n still owns the Telegram
webhook:

```bash
docker compose --profile candidate build hermes-gateway
docker compose --profile candidate up -d hermes-gateway
docker compose logs --tail=100 hermes-gateway
```

Do not enable webhook deletion during this phase. Long polling cannot consume
updates while the existing Telegram webhook is active.

## Queue uploader

Install `hermes-inbox-uploader.service` and its timer only after the separate
write remote has passed a controlled upload test. The uploader copies and
checks a snapshot of pending files before archiving them; failed uploads stay
in `pending` for retry.
