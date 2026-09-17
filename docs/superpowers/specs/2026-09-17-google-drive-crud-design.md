# Hermes Google Drive CRUD Design

## Goal

Hermes must handle explicit natural-language Google Drive requests directly, without treating `rclone` as the agent's CRUD interface. The first release covers file/folder list, read, create, update, delete, create-folder, and move operations while preserving the existing WIKI memo approval flow.

## Current gap

The repository currently searches and reads a locally mounted WIKI, writes approved memos to a local Inbox or queue, and has a separate `rclone copy` uploader. It has no Google Drive API client, no Drive tool in the registry, and no natural-language Drive route.

## Chosen approach

Use the Google Drive v3 REST API from a focused standard-library client. Authentication uses a runtime-only JSON credential file containing an OAuth refresh token and client credentials; the file is mounted read-only and never committed. The client refreshes access tokens in memory and injects an HTTP transport in tests, so CRUD behavior can be verified without network access or third-party dependencies.

The existing queue uploader remains available as a legacy fallback until the direct client passes Oracle smoke tests. It is not used by the new Drive route.

## Supported operations

`GoogleDriveClient` exposes:

- `list_files(name_contains, parent_id, page_size)`
- `read_file(file_id)`
- `create_file(name, content, parent_id, mime_type)`
- `update_file(file_id, content, name, mime_type)`
- `delete_file(file_id)`
- `create_folder(name, parent_id)`
- `move_file(file_id, parent_id, remove_parent_id)`

Text files are UTF-8 and default to `text/markdown`. Google Docs-native export is out of scope for this first slice; the client reports the API error instead of silently converting content.

## Authentication contract

`GOOGLE_DRIVE_CREDENTIALS_FILE` points to a JSON file with:

```json
{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "...",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

The access token is cached only in the process. `GOOGLE_DRIVE_ROOT_ID` is optional and supplies the default parent folder for create/list operations. A missing credential file fails closed with a user-readable configuration error.

## Natural-language contract

The router recognizes explicit Drive terms such as `구글드라이브`, `Google Drive`, and `GDrive`. It then recognizes the operation verb. File names should be supplied as `파일명: ...` or in quotes; create/update content should be supplied after `내용:`; file IDs can be supplied as `파일 ID: ...`. Ambiguous Drive requests return an instruction instead of falling through to WIKI or Codex.

Examples:

- `구글드라이브에서 파일명: 회의록.md 찾아줘`
- `구글드라이브 파일 ID: abc123 읽어줘`
- `구글드라이브에 파일명: 회의록.md 내용: 오늘 회의 결정사항을 저장해줘`
- `구글드라이브 파일 ID: abc123 내용: 수정된 본문으로 수정해줘`
- `구글드라이브 파일 ID: abc123 삭제해줘`
- `구글드라이브에 폴더명: 프로젝트A 폴더 만들어줘`

Create/read/list do not require a second confirmation. Update/delete/move require an explicit destructive/action verb and a resolvable file reference; missing fields are rejected before any API call.

## Error handling and safety

- Never log access tokens, refresh tokens, credential JSON, or Authorization headers.
- Convert HTTP failures into `GoogleDriveError` with status and a safe message.
- Escape user-provided name fragments before placing them in Drive query syntax.
- Do not overwrite a file during create; update requires an explicit update action.
- Do not delete by a broad name match. Name-based destructive requests must resolve to exactly one file; otherwise the gateway asks for a file ID or narrower query.

## Verification

- Unit tests cover token refresh, query escaping, every client operation, API errors, and the exact no-network transport calls.
- Router/gateway tests cover all natural-language operations and ambiguous/missing-field responses.
- Compose/config tests verify credentials are mounted read-only and are not baked into the image.
- Oracle verification is a separate smoke gate: read/list, create a uniquely named test file in `00_Inbox`, read it back, update it, then delete it and confirm it is gone. Hermes remains a candidate while n8n owns the Telegram webhook.
