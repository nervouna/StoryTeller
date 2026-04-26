"""Tests for the Secretary module."""

from storyteller.db.models import PowerTier
from storyteller.modules.secretary import (
    _extract_json,
    _outline_to_text,
    _parse_tier,
)
from storyteller.project.models import ChapterOutline, Outline


class TestExtractJson:
    def test_valid_json(self):
        assert _extract_json('{"a": 1}') == {"a": 1}

    def test_json_in_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert _extract_json(text) == {"a": 1}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"a": 1}\nDone.'
        assert _extract_json(text) == {"a": 1}

    def test_invalid_json(self):
        assert _extract_json("no json here") is None

    def test_empty_string(self):
        assert _extract_json("") is None


class TestParseTier:
    def test_exact_match(self):
        assert _parse_tier("金丹") == PowerTier.CORE

    def test_partial_match(self):
        assert _parse_tier("金丹初期") == PowerTier.CORE

    def test_empty(self):
        assert _parse_tier("") is None

    def test_no_match(self):
        assert _parse_tier("未知境界") is None


class TestOutlineToText:
    def test_basic_outline(self):
        outline = Outline(
            title="测试小说",
            genre="仙侠",
            logline="一个测试故事",
            themes=["成长", "冒险"],
            target_audience="男频读者",
            chapters=[
                ChapterOutline(
                    chapter_num=1,
                    title="开始",
                    summary="主角出场",
                    key_events=["拜师"],
                    characters_involved=["主角"],
                    setting="山门",
                ),
            ],
        )
        text = _outline_to_text(outline)
        assert "测试小说" in text
        assert "仙侠" in text
        assert "第1章" in text
        assert "主角出场" in text
        assert "拜师" in text
