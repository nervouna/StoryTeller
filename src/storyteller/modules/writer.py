"""Writer module (没头脑) — chapter drafting and revision."""
from __future__ import annotations

import re
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.config import Settings
from storyteller.db.engine import create_engine, get_session_factory
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import writer as writer_prompts
from storyteller.llm.tools import ALL_WORLD_TOOLS, handle_tool_call
from storyteller.log import get_logger
from storyteller.project.models import ChapterDraft, ProjectContext
from storyteller.utils.chinese import count_chinese_chars
from storyteller.utils.markdown import read_chapter

log = get_logger("writer")


async def writer_draft_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int | None = None,
    mode: Literal["draft", "revise"] = "draft",
    suggestions: str = "",
    original: str = "",
) -> ProjectContext:
    """Draft or revise one or more chapters.

    mode="draft": generate from outline
    mode="revise": rewrite `original` content following `suggestions`

    Updates ctx.chapters with results. Does NOT write to disk — caller owns I/O.
    """
    if not ctx.outline:
        log.error("No outline available")
        ctx.errors.append("Writer: no outline")
        return ctx

    llm_config = settings.get_llm("writer")
    client = create_client_from_config(llm_config)

    engine = await create_engine(ctx.db_path)
    factory = get_session_factory(engine)

    chapters_to_write = [chapter_num] if chapter_num else [ch.chapter_num for ch in ctx.outline.chapters]

    try:
        for ch_num in chapters_to_write:
            log.info("Writing chapter %d (mode=%s)...", ch_num, mode)
            async with factory() as session:
                draft = await _write_single_chapter(
                    ctx, client, session, ch_num,
                    mode=mode, suggestions=suggestions, original=original,
                )
                if draft:
                    _upsert_chapter(ctx, draft)
    finally:
        await engine.dispose()

    return ctx


def _upsert_chapter(ctx: ProjectContext, draft: ChapterDraft) -> None:
    for i, existing in enumerate(ctx.chapters):
        if existing.chapter_num == draft.chapter_num:
            ctx.chapters[i] = draft
            return
    ctx.chapters.append(draft)


async def _write_single_chapter(
    ctx: ProjectContext,
    client: LLMClient,
    session: AsyncSession,
    ch_num: int,
    mode: Literal["draft", "revise"] = "draft",
    suggestions: str = "",
    original: str = "",
) -> ChapterDraft | None:
    ch_outline = ctx.outline.get_chapter(ch_num)
    if not ch_outline:
        log.warning("No outline for chapter %d", ch_num)
        return None

    async def _tool_handler(name: str, input: dict) -> str:
        return await handle_tool_call(session, name, input)

    if mode == "revise":
        if not original:
            log.warning("Revise mode called without original for chapter %d", ch_num)
            return None
        system = writer_prompts.REVISE_SYSTEM
        user_prompt = writer_prompts.REVISE_USER.format(
            chapter_num=ch_num,
            original=original,
            suggestions=suggestions or "（无具体建议，保持原稿）",
        )
    else:
        previous_ending = ""
        if ch_num > 1:
            prev_content = read_chapter(ctx.project_dir, ch_num - 1)
            if prev_content:
                previous_ending = prev_content[-500:] if len(prev_content) > 500 else prev_content

        outline_text = f"标题: {ch_outline.title}\n摘要: {ch_outline.summary}"
        if ch_outline.key_events:
            outline_text += f"\n关键事件: {', '.join(ch_outline.key_events)}"
        if ch_outline.characters_involved:
            outline_text += f"\n出场人物: {', '.join(ch_outline.characters_involved)}"
        if ch_outline.setting:
            outline_text += f"\n地点: {ch_outline.setting}"

        system = writer_prompts.SYSTEM
        user_prompt = writer_prompts.USER.format(
            chapter_num=ch_num,
            chapter_outline=outline_text,
            previous_ending=previous_ending or "（这是第一章，没有前文）",
        )

    response = await client.call_with_tools_async(
        system=system,
        user=user_prompt,
        tools=ALL_WORLD_TOOLS,
        tool_handler=_tool_handler,
        max_rounds=5,
    )

    # Strip leading chapter heading (## or ### 第N章 xxx) if present
    title = ch_outline.title
    content = response
    heading_match = re.match(r"^#{2,3}\s+第\d+章\s*(.+?)\s*\n", response)
    if heading_match:
        title = heading_match.group(1).strip() or ch_outline.title
        content = response[heading_match.end():].strip()

    word_count = count_chinese_chars(content)

    return ChapterDraft(
        chapter_num=ch_num,
        title=title,
        content=content,
        word_count=word_count,
        status="draft",
    )
