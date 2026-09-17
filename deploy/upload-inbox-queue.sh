#!/usr/bin/env bash
set -euo pipefail

: "${HERMES_INBOX_QUEUE_DIR:?HERMES_INBOX_QUEUE_DIR is required}"
: "${HERMES_INBOX_REMOTE:?HERMES_INBOX_REMOTE is required}"
: "${HERMES_INBOX_LOCK_FILE:=/var/lock/hermes-inbox-uploader.lock}"

queue_dir="${HERMES_INBOX_QUEUE_DIR}"
pending_dir="${queue_dir}/pending"
uploaded_dir="${queue_dir}/uploaded"
mkdir -p "${pending_dir}" "${uploaded_dir}"

exec 9>"${HERMES_INBOX_LOCK_FILE}"
if ! flock -n 9; then
  exit 0
fi

snapshot="$(mktemp)"
cleanup() {
  rm -f "${snapshot}"
}
trap cleanup EXIT

find "${pending_dir}" -maxdepth 1 -type f -name '*.md' -printf '%f\n' \
  | sort > "${snapshot}"
if [ ! -s "${snapshot}" ]; then
  exit 0
fi

# Keep pending files until both the remote copy and a one-way content check pass.
rclone copy "${pending_dir}" "${HERMES_INBOX_REMOTE}" \
  --files-from "${snapshot}" \
  --ignore-existing \
  --checkers 4 \
  --transfers 1
rclone check "${pending_dir}" "${HERMES_INBOX_REMOTE}" \
  --files-from "${snapshot}" \
  --one-way \
  --checkers 4

while IFS= read -r filename; do
  [ -n "${filename}" ] || continue
  mv -- "${pending_dir}/${filename}" "${uploaded_dir}/${filename}"
done < "${snapshot}"
