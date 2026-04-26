"""Tests for project models."""
from pathlib import Path

from storyteller.project.models import (
    ChapterOutline,
    Outline,
    ProjectContext,
    TelescopeReport,
)


def test_outline_creation():
    outline = Outline(
        title="测试小说",
        genre="仙侠",
        logline="一个凡人修仙的故事",
    )
    assert outline.title == "测试小说"
    assert outline.genre == "仙侠"
    assert len(outline.chapters) == 0


def test_chapter_outline():
    ch = ChapterOutline(
        chapter_num=1,
        title="初入仙门",
        summary="主角进入修仙宗门",
        key_events=["拜师", "测试灵根"],
        characters_involved=["主角", "师父"],
    )
    assert ch.chapter_num == 1
    assert len(ch.key_events) == 2


def test_project_context(tmp_path: Path):
    ctx = ProjectContext(
        project_dir=tmp_path,
        db_path=tmp_path / "test.db",
    )
    assert ctx.outline is None
    assert len(ctx.chapters) == 0
    assert ctx.current_chapter == 0


def test_telescope_report():
    report = TelescopeReport(
        trends=["修仙题材火热", "系统流受欢迎"],
        popular_tropes=["废柴逆袭", "重生"],
    )
    assert len(report.trends) == 2
