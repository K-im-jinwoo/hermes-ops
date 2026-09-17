from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.memo_store import MemoSaveStatus, locate_wiki_repo_root, save_memo_to_inbox


def _make_wiki_repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "WIKI"
    content_root = repo_root / "wiki"
    (content_root / "00_Inbox").mkdir(parents=True)
    system_root = content_root / "90_System"
    system_root.mkdir()
    (repo_root / "AGENTS.md").write_text("# Test WIKI\n", encoding="utf-8")
    for name in (
        "WIKI_SCHEMA.md",
        "WORKFLOWS.md",
        "TEMPLATES.md",
        "VALIDATION.md",
        "tag-registry.md",
    ):
        (system_root / name).write_text("# Test\n", encoding="utf-8")
    return repo_root


def test_save_memo_creates_one_inbox_note_with_required_frontmatter(tmp_path: Path):
    repo_root = _make_wiki_repo(tmp_path)

    result = save_memo_to_inbox(
        "회의에서 Hermes 저장 단계를 정리했다",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 5),
    )

    assert result.status is MemoSaveStatus.CREATED
    assert result.path == Path("wiki/00_Inbox/2026-09-17_1405_회의에서-hermes-저장-단계를-정리했다.md")
    note = (repo_root / result.path).read_text(encoding="utf-8")
    assert note.startswith("---\n")
    assert "type: inbox\n" in note
    assert "status: draft\n" in note
    assert "source: telegram\n" in note
    assert "capture_kind: work\n" in note
    assert "회의에서 Hermes 저장 단계를 정리했다" in note


def test_save_memo_returns_duplicate_without_creating_second_note(tmp_path: Path):
    repo_root = _make_wiki_repo(tmp_path)
    first = save_memo_to_inbox(
        "같은 메모",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 5),
    )

    second = save_memo_to_inbox(
        "같은 메모",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 6),
    )

    assert first.status is MemoSaveStatus.CREATED
    assert second.status is MemoSaveStatus.DUPLICATE
    assert second.path == first.path
    assert len(list((repo_root / "wiki" / "00_Inbox").glob("*.md"))) == 1


def test_save_memo_does_not_overwrite_same_title_with_different_content(tmp_path: Path):
    repo_root = _make_wiki_repo(tmp_path)
    first = save_memo_to_inbox(
        "첫 번째 회의 내용",
        title="회의 메모",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 5),
    )

    second = save_memo_to_inbox(
        "두 번째 회의 내용",
        title="회의 메모",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 6),
    )

    assert first.status is MemoSaveStatus.CREATED
    assert second.status is MemoSaveStatus.NEEDS_REVIEW
    assert second.path == first.path


def test_save_memo_refuses_an_invalid_wiki_structure(tmp_path: Path):
    invalid_root = tmp_path / "not-a-wiki"
    invalid_root.mkdir()

    result = save_memo_to_inbox("저장하면 안 되는 메모", wiki_repo_root=invalid_root)

    assert result.status is MemoSaveStatus.UNAVAILABLE
    assert list(invalid_root.rglob("*.md")) == []


def test_save_memo_sanitizes_title_without_leaving_inbox(tmp_path: Path):
    repo_root = _make_wiki_repo(tmp_path)

    result = save_memo_to_inbox(
        "파일명 경계값",
        title="../비밀:메모?",
        wiki_repo_root=repo_root,
        now=datetime(2026, 9, 17, 14, 5),
    )

    assert result.status is MemoSaveStatus.CREATED
    assert result.path.parent == Path("wiki/00_Inbox")
    assert (repo_root / result.path).is_file()
    assert not (repo_root.parent / "비밀-메모.md").exists()


def test_locate_wiki_repo_root_accepts_a_configured_fixture(monkeypatch, tmp_path: Path):
    repo_root = _make_wiki_repo(tmp_path)
    monkeypatch.setenv("LLM_WIKI_ROOT", str(repo_root))

    assert locate_wiki_repo_root() == repo_root.resolve()
