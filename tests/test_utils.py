"""Tests for utility functions."""
from storyteller.utils.chinese import count_chinese_chars, split_chapter


def test_count_chinese_chars():
    assert count_chinese_chars("你好世界") == 4
    assert count_chinese_chars("Hello 你好") == 2
    assert count_chinese_chars("") == 0
    assert count_chinese_chars("123abc") == 0


def test_split_chapter():
    text = "段落一\n\n段落二\n\n段落三\n\n段落四"
    parts = split_chapter(text, target_chars=10)
    assert len(parts) >= 1


def test_split_chapter_long():
    # Create a long text
    para = "这是一个很长的段落。" * 100
    text = f"{para}\n\n{para}\n\n{para}"
    parts = split_chapter(text, target_chars=200)
    assert len(parts) > 1
