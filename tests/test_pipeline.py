"""Tests for pipeline modules (critic, qa, idea_king, writer)."""
from pathlib import Path

from storyteller.modules.critic import _parse_review
from storyteller.modules.idea_king import (
    _outline_to_markdown,
    _parse_outline_data,
    load_outline_from_file,
)
from storyteller.modules.qa import _parse_qa_response
from storyteller.project.models import ChapterOutline, Outline


class TestParseReview:
    def test_parse_sections(self):
        text = "## 审核意见\n问题很多\n## 修改建议\n重写吧\n## 润色后版本\n最终文本"
        result = _parse_review(text)
        assert result["审核意见"] == "问题很多"
        assert result["修改建议"] == "重写吧"
        assert result["润色后版本"] == "最终文本"

    def test_empty(self):
        assert _parse_review("") == {}

    def test_no_headers(self):
        assert _parse_review("just plain text") == {}


class TestParseQaResponse:
    def test_parse_sections(self):
        text = "## 调整说明\n拆分了\n## 正文\n调整后的内容"
        result = _parse_qa_response(text)
        assert result["调整说明"] == "拆分了"
        assert result["正文"] == "调整后的内容"


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
        assert "{num_chapters}" in EXTEND_SYSTEM

    def test_extend_user_has_template_vars(self):
        from storyteller.llm.prompts.idea_king import EXTEND_USER
        assert "{outline_text}" in EXTEND_USER
        assert "{next_chapter_num}" in EXTEND_USER
        assert "{num_chapters}" in EXTEND_USER

    def test_extend_system_mentions_json(self):
        from storyteller.llm.prompts.idea_king import EXTEND_SYSTEM
        assert "JSON" in EXTEND_SYSTEM
