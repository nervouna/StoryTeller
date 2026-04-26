"""QA module (质检员) — format chapters to web novel standard."""
from __future__ import annotations

import re

from storyteller.config import Settings
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import qa as qa_prompts
from storyteller.log import get_logger
from storyteller.project.models import ProjectContext
from storyteller.utils.chinese import count_chinese_chars, split_chapter
from storyteller.utils.markdown import list_chapters, read_chapter, write_chapter

log = get_logger("qa")

TARGET_MIN = 2000
TARGET_MAX = 3000


async def qa_format_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int | None = None,
) -> ProjectContext:
    """Format chapter(s) to web novel standard length."""
    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    chapters_to_process = []
    if chapter_num:
        chapters_to_process = [chapter_num]
    else:
        # Process all reviewed or draft chapters
        for draft in ctx.chapters:
            if draft.status in ("draft", "reviewed"):
                chapters_to_process.append(draft.chapter_num)
        if not chapters_to_process:
            chapters_to_process = [num for num, _ in list_chapters(ctx.project_dir)]

    for ch_num in chapters_to_process:
        log.info("QA formatting chapter %d...", ch_num)
        await _format_single_chapter(ctx, settings, client, ch_num)

    return ctx


async def _format_single_chapter(
    ctx: ProjectContext,
    settings: Settings,
    client: LLMClient,
    ch_num: int,
) -> None:
    """Format a single chapter."""
    # Get content
    content = read_chapter(ctx.project_dir, ch_num)
    if not content:
        for draft in ctx.chapters:
            if draft.chapter_num == ch_num:
                content = draft.content
                break
    if not content:
        log.warning("No content for chapter %d", ch_num)
        return

    char_count = count_chinese_chars(content)

    # Check if adjustment needed
    if TARGET_MIN <= char_count <= TARGET_MAX:
        log.info("Chapter %d already within target: %d chars", ch_num, char_count)
        # Still update status
        for draft in ctx.chapters:
            if draft.chapter_num == ch_num:
                draft.status = "final"
                draft.word_count = char_count
                break
        return

    # Use LLM to adjust
    response = client.call(
        system=qa_prompts.SYSTEM,
        user=qa_prompts.USER.format(
            chapter_num=ch_num,
            chapter_content=content,
            current_chars=char_count,
        ),
    )

    # Parse response
    sections = _parse_qa_response(response)
    adjusted = sections.get("正文", "")
    explanation = sections.get("调整说明", "")

    if adjusted:
        new_count = count_chinese_chars(adjusted)
        log.info("Chapter %d adjusted: %d → %d chars (%s)", ch_num, char_count, new_count, explanation)

        # Extract title from content
        title = ""
        title_match = re.search(r"^# (.+)$", content, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
        # Also try ## format
        if not title:
            title_match = re.search(r"^## 第\d+章\s*(.+)$", content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

        write_chapter(ctx.project_dir, ch_num, title, adjusted)

        # Update in-memory
        for draft in ctx.chapters:
            if draft.chapter_num == ch_num:
                draft.content = adjusted
                draft.word_count = new_count
                draft.status = "final"
                break
    else:
        log.warning("Chapter %d: LLM did not produce adjusted content", ch_num)
        # Fallback: try mechanical split/merge
        if char_count > TARGET_MAX:
            parts = split_chapter(content, TARGET_MAX)
            if len(parts) > 1:
                log.info("Mechanical split into %d parts", len(parts))
                # Keep first part as this chapter, save rest as bonus
                write_chapter(ctx.project_dir, ch_num, "", parts[0])
                for i, part in enumerate(parts[1:], 1):
                    write_chapter(ctx.project_dir, ch_num + i, "续", part)
        elif char_count < TARGET_MIN:
            log.warning("Chapter %d too short (%d chars), manual review needed", ch_num, char_count)


def _parse_qa_response(text: str) -> dict[str, str]:
    """Parse QA response into sections."""
    from storyteller.utils.markdown import parse_sections
    return parse_sections(text)
