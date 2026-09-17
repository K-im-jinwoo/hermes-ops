# Google Drive CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a direct, natural-language Google Drive CRUD tool to Hermes while keeping credentials outside the repository and preserving the existing memo approval flow.

**Architecture:** A standard-library Google Drive REST client owns authentication, request construction, and CRUD methods. The intent router parses explicit Drive operations into a small request object, and the Telegram gateway formats results and rejects ambiguous or incomplete destructive requests before calling the client. The legacy queue uploader remains unchanged until live smoke validation passes.

**Tech Stack:** Python 3.12 standard library (`urllib`, `json`, `dataclasses`), pytest, PyYAML, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-17-google-drive-crud-design.md`

## Global Constraints

- Credentials are runtime-only and must never be committed or logged.
- No third-party Google SDK dependency is added; HTTP transport is injectable for tests.
- Existing natural-language `/ask` behavior and memo approval behavior remain compatible.
- No Telegram webhook cutover or n8n shutdown is performed by this change.
- Name-based update/delete must resolve to exactly one Drive file before mutation.

---

### Task 1: Add the token provider and Drive REST client

**Files:**
- Create: `tools/google_drive_tool.py`
- Test: `tests/test_google_drive_tool.py`

**Interfaces:**
- Produces `GoogleDriveClient`, `GoogleDriveError`, `DriveFile`, and `load_google_drive_client()`.
- `GoogleDriveClient` methods: `list_files`, `read_file`, `create_file`, `update_file`, `delete_file`, `create_folder`, `move_file`.
- `load_google_drive_client()` reads `GOOGLE_DRIVE_CREDENTIALS_FILE` and `GOOGLE_DRIVE_ROOT_ID`.

- [ ] **Step 1: Write failing tests for token loading and refresh.**
  - Use a temporary JSON credential file and a fake transport.
  - Assert a token endpoint POST is made with `grant_type=refresh_token`, `client_id`, `client_secret`, and `refresh_token`.
  - Assert the returned access token is reused for a second API call without a second refresh until expiry.
  - Assert missing credentials produce a safe configuration error.
- [ ] **Step 2: Run the focused tests and verify the expected missing-module failure.**

  Run: `python -m pytest -q tests/test_google_drive_tool.py`

  Expected: collection/import failure because `tools.google_drive_tool` does not exist yet.
- [ ] **Step 3: Write failing tests for list/read/create/update/delete/folder/move request behavior.**
  - Use a fake transport that records method, URL, query parameters, headers, and bytes body.
  - Assert list requests include `trashed = false`, escaped `name contains`, parent filtering, and page size.
  - Assert read uses `alt=media` and returns UTF-8 text.
  - Assert create and update send metadata/media with the correct MIME type.
  - Assert delete and move use the correct Drive API query parameters.
  - Assert non-2xx responses raise `GoogleDriveError` without exposing authorization values.
- [ ] **Step 4: Run the focused tests and verify they fail for the unimplemented client.**

  Run: `python -m pytest -q tests/test_google_drive_tool.py`

  Expected: assertion failures for missing client methods and request behavior.
- [ ] **Step 5: Implement the minimal token provider and REST client.**
  - Keep all network calls behind an injectable transport callable.
  - Use `https://www.googleapis.com/drive/v3` and `/upload/drive/v3` defaults.
  - Cache refreshed access tokens in memory only.
  - Use multipart upload for create and media upload plus metadata patch for update.
  - Escape Drive query literals and return typed `DriveFile` records.
- [ ] **Step 6: Run the focused tests and verify green.**

  Run: `python -m pytest -q tests/test_google_drive_tool.py`

  Expected: all focused Drive client tests pass.
- [ ] **Step 7: Refactor only after green.**
  - Extract small URL/query/header helpers if duplication remains.
  - Re-run `python -m pytest -q tests/test_google_drive_tool.py`.
- [ ] **Step 8: Commit the client and tests.**

  Run: `git add tools/google_drive_tool.py tests/test_google_drive_tool.py && git commit -m "feat: add direct Google Drive CRUD client"`

### Task 2: Add natural-language Drive request parsing

**Files:**
- Modify: `intent_router.py`
- Create: `tools/google_drive_request.py`
- Test: `tests/test_google_drive_request.py`
- Modify: `tests/test_intent_router.py`

**Interfaces:**
- Produces `IntentKind.GOOGLE_DRIVE` and `parse_google_drive_request(prompt)`.
- `GoogleDriveRequest` contains `action`, `file_id`, `file_name`, `folder_name`, `parent_id`, `query`, and `content`.

- [ ] **Step 1: Write failing parser and classifier tests.**
  - Cover Korean and English Drive terms.
  - Cover list, read, create, update, delete, create-folder, and move actions.
  - Cover `파일명:`, quoted names, `파일 ID:`, `폴더명:`, `상위 폴더 ID:`, and `내용:` extraction.
  - Assert non-Drive WIKI and memo prompts keep their existing routes.
- [ ] **Step 2: Run the focused tests and verify they fail.**

  Run: `python -m pytest -q tests/test_google_drive_request.py tests/test_intent_router.py`

  Expected: missing enum/parser failures for the new Drive cases, while existing tests remain meaningful.
- [ ] **Step 3: Implement the smallest parser that satisfies the tests.**
  - Check Drive terms before WIKI/memo fallbacks only when a Drive operation phrase is present.
  - Return `CLARIFY` for Drive prompts with no recognized action.
  - Preserve the existing `Intent` constructor compatibility.
- [ ] **Step 4: Run focused tests and verify green.**
- [ ] **Step 5: Commit the router/parser.**

  Run: `git add intent_router.py tools/google_drive_request.py tests/test_google_drive_request.py tests/test_intent_router.py && git commit -m "feat: route natural language Google Drive requests"`

### Task 3: Connect Drive requests to the Telegram gateway and tool registry

**Files:**
- Modify: `telegram_gateway.py`
- Modify: `scripts/verify_tool_calling.py`
- Modify: `config/hermes_config.yaml`
- Create: `tests/test_gateway_drive.py`
- Modify: `tests/test_gateway_routing.py`

**Interfaces:**
- Gateway uses a lazy `load_google_drive_client()` so import and existing non-Drive tests do not require credentials.
- Gateway resolves name references only for read/list/create; update/delete/move require exactly one match or an explicit ID.
- Registry exposes one `google_drive` operation schema with `action`, `file_id`, `file_name`, `content`, and `parent_id` fields.

- [ ] **Step 1: Write failing gateway tests.**
  - Inject a fake Drive client into the gateway.
  - Assert list/read/create/update/delete/folder/move natural-language requests call the expected client method.
  - Assert missing credentials return a safe configuration message.
  - Assert ambiguous name-based delete/update does not call the client mutation method.
  - Assert existing memo approval and WIKI read tests retain their behavior.
- [ ] **Step 2: Run the gateway tests and verify the new tests fail.**

  Run: `python -m pytest -q tests/test_gateway_drive.py tests/test_gateway_routing.py`

  Expected: Drive requests currently return the generic clarification response.
- [ ] **Step 3: Implement gateway dispatch and safe formatting.**
  - Add the Drive branch to `process_user_prompt`.
  - Format file lists and file content without exposing tokens.
  - Require name/content/reference fields before API calls.
  - Map `GoogleDriveError` to Korean user-readable errors with status-safe detail.
- [ ] **Step 4: Add the generic registry tool and configuration entry.**
- [ ] **Step 5: Run focused gateway and registry tests and verify green.**
- [ ] **Step 6: Commit the integration.**

  Run: `git add telegram_gateway.py scripts/verify_tool_calling.py config/hermes_config.yaml tests/test_gateway_drive.py tests/test_gateway_routing.py && git commit -m "feat: connect Hermes to Google Drive operations"`

### Task 4: Add runtime configuration and deployment documentation

**Files:**
- Modify: `.env.example`
- Modify: `deploy/compose.yaml`
- Modify: `deploy/README.md`
- Modify: `tests/test_deploy_config.py`

**Interfaces:**
- Runtime variable `GOOGLE_DRIVE_CREDENTIALS_FILE` points at a read-only mounted JSON credential file.
- Runtime variable `GOOGLE_DRIVE_ROOT_ID` optionally scopes default operations to the WIKI root or `00_Inbox`.

- [ ] **Step 1: Write failing deployment assertions.**
  - Assert the credentials mount is read-only and not copied by the Dockerfile.
  - Assert the Drive credential path is injected into the service environment.
  - Assert README documents the credential JSON shape, permission requirements, and candidate smoke sequence.
- [ ] **Step 2: Run deployment tests and verify the new assertions fail.**
- [ ] **Step 3: Add the environment example, read-only mount, and updated deployment instructions.**
  - Do not add credentials to the image or Git.
  - Keep candidate profile and webhook deletion behavior unchanged.
  - Mark the rclone queue as legacy fallback, not the Hermes CRUD interface.
- [ ] **Step 4: Run deployment tests and Compose config validation.**

  Run: `python -m pytest -q tests/test_deploy_config.py`

  Run: `docker compose -f deploy/compose.yaml config --quiet`

- [ ] **Step 5: Commit deployment configuration and documentation.**

  Run: `git add .env.example deploy/compose.yaml deploy/README.md tests/test_deploy_config.py && git commit -m "docs: configure direct Google Drive credentials"`

### Task 5: Full verification and Oracle candidate smoke preparation

**Files:**
- No new production files; inspect the complete Git diff and committed state.

- [ ] **Step 1: Run the full local test suite excluding the known inaccessible real-WIKI test.**

  Run: `python -m pytest -q -k "not test_search_real_wiki_returns_results"`

- [ ] **Step 2: Run compile and whitespace checks.**

  Run: `python -m compileall -q .`

  Run: `git diff --check HEAD~4..HEAD`

- [ ] **Step 3: Build the candidate image locally or on Oracle without starting Telegram cutover.**
  - Confirm the image contains no credential file.
  - Confirm the Drive credential is mounted read-only at runtime.
- [ ] **Step 4: Prepare, but do not execute without credentials, the Oracle smoke sequence.**
  - Place the OAuth JSON at `/srv/hermes-ops/google-drive-credentials.json` with mode `0600` and readable by the Hermes runtime UID.
  - Set `GOOGLE_DRIVE_ROOT_ID` to the intended WIKI folder or `00_Inbox`.
  - Start only the candidate profile while n8n remains the Telegram receiver.
  - Test list/read/create/update/read/delete/list using a unique `hermes-crud-smoke-<timestamp>.md` file.
- [ ] **Step 5: Report verified local results, unverified live gates, and the exact next approval needed before n8n cutover.**
