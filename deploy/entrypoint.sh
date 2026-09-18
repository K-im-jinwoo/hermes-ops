#!/bin/sh
set -eu

if [ -n "${GEMINI_API_KEY_FILE:-}" ]; then
  if [ ! -r "${GEMINI_API_KEY_FILE}" ]; then
    echo "GEMINI_API_KEY_FILE is not readable" >&2
    exit 1
  fi
  GEMINI_API_KEY="$(cat "${GEMINI_API_KEY_FILE}")"
  if [ -z "${GEMINI_API_KEY}" ]; then
    echo "GEMINI_API_KEY_FILE is empty" >&2
    exit 1
  fi
  export GEMINI_API_KEY
fi

exec python /app/telegram_gateway.py
