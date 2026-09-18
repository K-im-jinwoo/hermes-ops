from __future__ import annotations

import os
from pathlib import Path
import time


def heartbeat_is_fresh(path: Path, *, max_age_seconds: int) -> bool:
    if max_age_seconds <= 0:
        return False
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds <= max_age_seconds


def main() -> int:
    path = Path(os.getenv("HERMES_HEARTBEAT_PATH", "/var/lib/hermes/state/heartbeat"))
    try:
        max_age_seconds = int(os.getenv("HERMES_HEARTBEAT_MAX_AGE_SECONDS", "120"))
    except ValueError:
        return 1
    return 0 if heartbeat_is_fresh(path, max_age_seconds=max_age_seconds) else 1


if __name__ == "__main__":
    raise SystemExit(main())
