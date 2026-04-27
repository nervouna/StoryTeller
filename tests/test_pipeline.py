"""Tests for pipeline modules (critic, qa, idea_king, writer)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from storyteller.modules.idea_king import (
    _outline_to_markdown,
    _parse_outline_data,
    load_outline_from_file,
)
from storyteller.project.models import ChapterOutline, Outline, ProjectContext
from storyteller.utils.markdown import parse_sections


class TestParseReview:
    def test_parse_sections(self):
        text = "## 审核意见\n🔴 问题一\n🟡 问题二\n\n## 修改建议\n1. 改 A\n2. 改 B"
        result = parse_sections(text)
        assert "🔴 问题一" in result["审核意见"]
        assert "🟡 问题二" in result["审核意见"]
        assert "1. 改 A" in result["修改建议"]

    def test_empty(self):
        assert parse_sections("") == {}

    def test_no_headers(self):
        assert parse_sections("just plain text") == {}


class TestParseQaResponse:
    def test_parse_sections(self):
        text = "## 调整建议\n1. 精简前半段\n2. 补充细节"
        result = parse_sections(text)
        assert "精简前半段" in result["调整建议"]

    def test_no_change(self):
        text = "## 调整建议\n无需调整"
        result = parse_sections(text)
        assert result["调整建议"] == "无需调整"


class TestParseOutlineData:
    def test_basic(self):
        data = {
            "title": "测试",
            "genre": "仙侠",
            "logline": "故事",
            "themes": ["成长"],
            "target_audience": "男频",
            "notes": "世界观",
            "chapters": [
                {"chapter_num": 1, "title": "第一章", "summary": "摘要", "key_events": ["事件1"], "characters_involved": ["角色1"], "setting": "地点1"},
            ],
        }
        outline = _parse_outline_data(data)
        assert outline.title == "测试"
        assert outline.genre == "仙侠"
        assert len(outline.chapters) == 1
        assert outline.chapters[0].title == "第一章"
        assert outline.chapters[0].key_events == ["事件1"]

    def test_missing_fields(self):
        data = {"title": "测试", "chapters": []}
        outline = _parse_outline_data(data)
        assert outline.title == "测试"
        assert outline.genre == ""
        assert outline.chapters == []


class TestOutlineToMarkdown:
    def test_roundtrip(self):
        outline = Outline(
            title="测试小说",
            genre="仙侠",
            logline="故事概括",
            themes=["成长"],
            target_audience="男频",
            notes="世界观描述",
            chapters=[
                ChapterOutline(chapter_num=1, title="开始", summary="摘要", key_events=["事件"], characters_involved=["角色"], setting="地点"),
            ],
        )
        md = _outline_to_markdown(outline)
        assert "# 测试小说" in md
        assert "仙侠" in md
        assert "第1章" in md
        assert "摘要" in md


class TestLoadOutlineFromFile:
    def test_load_existing(self, tmp_path: Path):
        outline_md = """# 测试小说

- **类型**: 仙侠
- **一句话概括**: 一个故事
- **核心主题**: 成长, 冒险
- **目标读者**: 男频

## 世界观概述
这是一个测试世界。

## 章节大纲

### 第1章 - 开始
**摘要**: 主角出场
**关键事件**: 拜师, 测试
**出场人物**: 主角, 师父
**地点**: 山门
"""
        (tmp_path / "outline.md").write_text(outline_md, encoding="utf-8")
        outline = load_outline_from_file(tmp_path)
        assert outline is not None
        assert outline.title == "测试小说"
        assert outline.genre == "仙侠"
        assert len(outline.chapters) == 1
        assert outline.chapters[0].summary == "主角出场"
        assert outline.chapters[0].characters_involved == ["主角", "师父"]

    def test_load_nonexistent(self, tmp_path: Path):
        assert load_outline_from_file(tmp_path) is None

    def test_load_empty(self, tmp_path: Path):
        (tmp_path / "outline.md").write_text("", encoding="utf-8")
        assert load_outline_from_file(tmp_path) is None

    def test_load_no_chapters(self, tmp_path: Path):
        (tmp_path / "outline.md").write_text("# name\n\n只有标题没有章节\n", encoding="utf-8")
        outline = load_outline_from_file(tmp_path)
        assert outline is not None
        assert outline.title == "name"
        assert outline.chapters == []


class TestExtendPrompts:
    def test_extend_system_exists(self):
        from storyteller.llm.prompts.idea_king import EXTEND_SYSTEM
        assert EXTEND_SYSTEM

    def test_extend_system_has_template_vars(self):
        from storyteller.llm.prompts.idea_king import EXTEND_SYSTEM
        assert "{batch_size}" in EXTEND_SYSTEM
        assert "{next_chapter}" in EXTEND_SYSTEM

    def test_extend_user_has_template_vars(self):
        from storyteller.llm.prompts.idea_king import EXTEND_USER
        assert "{outline_text}" in EXTEND_USER
        assert "{next_chapter}" in EXTEND_USER
        assert "{batch_size}" in EXTEND_USER
        assert "{recent_chapters}" in EXTEND_USER
        assert "{world_summary}" in EXTEND_USER

    def test_extend_system_mentions_json(self):
        from storyteller.llm.prompts.idea_king import EXTEND_SYSTEM
        assert "JSON" in EXTEND_SYSTEM


class TestIdeaKingExtend:
    @pytest.mark.asyncio
    async def test_extend_raises_when_no_outline(self, tmp_project: Path):
        from storyteller.modules.idea_king import idea_king_extend

        ctx = ProjectContext(project_dir=tmp_project, db_path=tmp_project / "test.db")
        settings = MagicMock()
        with pytest.raises(ValueError, match="No outline"):
            await idea_king_extend(ctx, settings, target_chapter=5)

    @pytest.mark.asyncio
    async def test_extend_no_op_when_already_sufficient(self, tmp_project: Path):
        from storyteller.modules.idea_king import idea_king_extend

        outline = Outline(
            title="测试",
            chapters=[
                ChapterOutline(chapter_num=1, title="第一章", summary="摘要1"),
                ChapterOutline(chapter_num=2, title="第二章", summary="摘要2"),
            ],
        )
        ctx = ProjectContext(project_dir=tmp_project, db_path=tmp_project / "test.db", outline=outline)
        settings = MagicMock()

        result = await idea_king_extend(ctx, settings, target_chapter=2)
        assert len(result.outline.chapters) == 2
        settings.get_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_extend_adds_new_chapters(self, tmp_project: Path):
        from storyteller.modules.idea_king import idea_king_extend

        outline = Outline(
            title="测试",
            chapters=[ChapterOutline(chapter_num=1, title="第一章", summary="摘要")],
        )
        from storyteller.utils.markdown import write_outline
        write_outline(tmp_project, _outline_to_markdown(outline))

        ctx = ProjectContext(project_dir=tmp_project, db_path=tmp_project / "test.db", outline=outline)
        settings = MagicMock()

        mock_response = {
            "chapters": [
                {"chapter_num": 2, "title": "第二章", "summary": "摘要2"},
                {"chapter_num": 3, "title": "第三章", "summary": "摘要3"},
            ]
        }

        with patch("storyteller.modules.idea_king.create_client_from_config") as mock_factory:
            mock_client = MagicMock()
            mock_client.call_json.return_value = mock_response
            mock_factory.return_value = mock_client

            result = await idea_king_extend(ctx, settings, target_chapter=3)

        assert len(result.outline.chapters) == 3
        assert result.outline.chapters[1].title == "第二章"
        assert result.outline.chapters[2].chapter_num == 3

    @pytest.mark.asyncio
    async def test_extend_filters_overlapping_chapters(self, tmp_project: Path):
        from storyteller.modules.idea_king import idea_king_extend

        outline = Outline(
            title="测试",
            chapters=[
                ChapterOutline(chapter_num=1, title="第一章", summary="摘要"),
                ChapterOutline(chapter_num=2, title="第二章", summary="摘要"),
            ],
        )
        from storyteller.utils.markdown import write_outline
        write_outline(tmp_project, _outline_to_markdown(outline))

        ctx = ProjectContext(project_dir=tmp_project, db_path=tmp_project / "test.db", outline=outline)
        settings = MagicMock()

        # LLM returns chapter 2 again (overlap) + chapter 3 (new)
        mock_response = {
            "chapters": [
                {"chapter_num": 2, "title": "重复章节", "summary": "不应该出现"},
                {"chapter_num": 3, "title": "第三章", "summary": "新内容"},
            ]
        }

        with patch("storyteller.modules.idea_king.create_client_from_config") as mock_factory:
            mock_client = MagicMock()
            mock_client.call_json.return_value = mock_response
            mock_factory.return_value = mock_client

            result = await idea_king_extend(ctx, settings, target_chapter=3)

        assert len(result.outline.chapters) == 3
        assert result.outline.chapters[2].title == "第三章"

    @pytest.mark.asyncio
    async def test_extend_saves_outline_to_disk(self, tmp_project: Path):
        from storyteller.modules.idea_king import idea_king_extend

        outline = Outline(
            title="测试",
            chapters=[ChapterOutline(chapter_num=1, title="第一章", summary="摘要")],
        )
        from storyteller.utils.markdown import write_outline
        write_outline(tmp_project, _outline_to_markdown(outline))

        ctx = ProjectContext(project_dir=tmp_project, db_path=tmp_project / "test.db", outline=outline)
        settings = MagicMock()

        mock_response = {
            "chapters": [{"chapter_num": 2, "title": "续篇", "summary": "续篇摘要"}]
        }

        with patch("storyteller.modules.idea_king.create_client_from_config") as mock_factory:
            mock_client = MagicMock()
            mock_client.call_json.return_value = mock_response
            mock_factory.return_value = mock_client

            await idea_king_extend(ctx, settings, target_chapter=2)

        reloaded = load_outline_from_file(tmp_project)
        assert reloaded is not None
        assert len(reloaded.chapters) == 2
        assert reloaded.chapters[1].title == "续篇"
