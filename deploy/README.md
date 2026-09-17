# Oracle deployment

This deployment keeps the Hermes process separate from Google Drive write
credentials.

## Runtime boundary

- `hermes-gateway` reads the synchronized WIKI at `/srv/llm-wiki/current`.
- Approved memos are written to `/srv/hermes-ops/queue/pending` only.
- `upload-inbox-queue.sh` is the only component that needs a write-capable
  `rclone` remote.
- The existing `wiki-drive` remote is read-only and must not be reused for
  uploads.
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
/srv/hermes-ops/uploader.env
```

The bot token file must be mode `0600` and must not be committed. The
`uploader.env` file must contain only runtime configuration, for example:

```text
HERMES_INBOX_QUEUE_DIR=/srv/hermes-ops/queue
HERMES_INBOX_REMOTE=wiki-drive-write:
HERMES_INBOX_LOCK_FILE=/var/lock/hermes-inbox-uploader.lock
```

Configure `wiki-drive-write` with the Google Drive `00_Inbox` folder ID as its
`root_folder_id`. This makes the remote root equal to `WIKI/wiki/00_Inbox` and
avoids giving the uploader a path through the rest of the WIKI tree. The
`wiki-drive-write` remote is intentionally a placeholder until a separate
write identity is provisioned and verified.

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
