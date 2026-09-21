from datetime import datetime, timedelta, timezone

import pytest

from tools.task_selection import TaskSelectionError, TaskSelectionStore


def _brief():
    return {"recommended": [{"text": "첫째"}, {"text": "둘째"}, {"text": "셋째"}]}


def test_selection_is_identity_bound_validated_and_single_use(tmp_path):
    store = TaskSelectionStore(tmp_path / "state.sqlite3")
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    pending = store.issue(user_id="u1", chat_id="c1", brief=_brief(), now=now)

    assert store.consume(
        pending.selection_id,
        user_id="other",
        chat_id="c1",
        selected_indices=(1,),
        now=now,
    ) is None
    with pytest.raises(TaskSelectionError, match="추천 목록"):
        store.consume(
            pending.selection_id,
            user_id="u1",
            chat_id="c1",
            selected_indices=(4,),
            now=now,
        )
    assert store.consume(
        pending.selection_id,
        user_id="u1",
        chat_id="c1",
        selected_indices=(1, 3),
        now=now,
    ).brief == _brief()
    assert store.consume(
        pending.selection_id,
        user_id="u1",
        chat_id="c1",
        selected_indices=(1,),
        now=now,
    ) is None


def test_expired_selection_is_not_consumed(tmp_path):
    store = TaskSelectionStore(tmp_path / "state.sqlite3", ttl_seconds=60)
    now = datetime(2026, 9, 21, tzinfo=timezone.utc)
    pending = store.issue(user_id="u1", chat_id="c1", brief=_brief(), now=now)

    assert store.consume(
        pending.selection_id,
        user_id="u1",
        chat_id="c1",
        selected_indices=(1,),
        now=now + timedelta(seconds=61),
    ) is None
