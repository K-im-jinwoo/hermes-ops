from __future__ import annotations

import os
import time

import healthcheck


def test_missing_heartbeat_is_unhealthy(tmp_path):
    assert healthcheck.heartbeat_is_fresh(tmp_path / "missing", max_age_seconds=120) is False


def test_recent_heartbeat_is_healthy(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    heartbeat.touch()

    assert healthcheck.heartbeat_is_fresh(heartbeat, max_age_seconds=120) is True


def test_stale_heartbeat_is_unhealthy(tmp_path):
    heartbeat = tmp_path / "heartbeat"
    heartbeat.touch()
    stale = time.time() - 121
    os.utime(heartbeat, (stale, stale))

    assert healthcheck.heartbeat_is_fresh(heartbeat, max_age_seconds=120) is False
