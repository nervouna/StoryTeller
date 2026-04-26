"""Writer module (没头脑) — chapter drafting."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.config import Settings
from storyteller.db.engine import create_engine, get_session_factory
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import writer as writer_prompts
from storyteller.llm.tools import ALL_WORLD_TOOLS, handle_tool_call
from storyteller.log import get_logger
from storyteller.project.models import ChapterDraft, ProjectContext
from storyteller.utils.chinese import count_chinese_chars
from storyteller.utils.markdown import read_chapter, write_chapter

log = get_logger("writer")


async def writer_draft_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int | None = None,
) -> ProjectContext:
    """Draft one or all chapters.

    Uses LLM with tool-use to query world-building DB for consistency.
    """
    if not ctx.outline:
        log.error("No outline available")
        ctx.errors.append("Writer: no outline")
        return ctx

    llm_config = settings.get_llm("writer")
    client = create_client_from_config(llm_config)

    # Initialize DB engine
    engine = await create_engine(ctx.db_path)
    factory = get_session_factory(engine)

    chapters_to_write = []
    chapters_to_write = [chapter_num] if chapter_num else [ch.chapter_num for ch in ctx.outline.chapters]

    for ch_num in chapters_to_write:
        log.info("Writing chapter %d...", ch_num)
        async with factory() as session:
            draft = await _write_single_chapter(ctx, settings, client, session, ch_num)
            if draft:
                ctx.chapters.append(draft)
                # Save to disk
                path = write_chapter(ctx.project_dir, ch_num, draft.title, draft.content)
                log.info("Chapter %d saved: %d chars → %s", ch_num, draft.word_count, path)

    return ctx


async def _write_single_chapter(
    ctx: ProjectContext,
    settings: Settings,
    client: LLMClient,
    session: AsyncSession,
    ch_num: int,
) -> ChapterDraft | None:
    """Write a single chapter with tool-use for world context."""
    # Find chapter outline
    ch_outline = None
    for ch in ctx.outline.chapters:
        if ch.chapter_num == ch_num:
            ch_outline = ch
            break
    if not ch_outline:
        log.warning("No outline for chapter %d", ch_num)
        return None

    # Build previous chapter ending
    previous_ending = ""
    if ch_num > 1:
        prev_content = read_chapter(ctx.project_dir, ch_num - 1)
        if prev_content:
            # Take last 500 chars
            previous_ending = prev_content[-500:] if len(prev_content) > 500 else prev_content

    # Build context
    outline_text = f"标题: {ch_outline.title}\n摘要: {ch_outline.summary}"
    if ch_outline.key_events:
        outline_text += f"\n关键事件: {', '.join(ch_outline.key_events)}"
    if ch_outline.characters_involved:
        outline_text += f"\n出场人物: {', '.join(ch_outline.characters_involved)}"
    if ch_outline.setting:
        outline_text += f"\n地点: {ch_outline.setting}"

    user_prompt = writer_prompts.USER.format(
        chapter_num=ch_num,
        chapter_outline=outline_text,
        previous_ending=previous_ending or "（这是第一章，没有前文）",
    )

    # Tool handler using session (async — no run_until_complete bridge)
    async def _tool_handler(name: str, input: dict) -> str:
        return await handle_tool_call(session, name, input)

    response = await client.call_with_tools_async(
        system=writer_prompts.SYSTEM,
        user=user_prompt,
        tools=ALL_WORLD_TOOLS,
        tool_handler=_tool_handler,
        max_rounds=5,
    )

    # Parse response — extract chapter title and content
    title = ch_outline.title
    content = response

    # Try to extract title from ## header
    import re
    title_match = re.search(r"## 第\d+章\s*(.+)", response)
    if title_match:
        title = title_match.group(1).strip()
        # Content is everything after the title line
        content_start = title_match.end()
        content = response[content_start:].strip()

    # Clean up any ## markers that aren't part of the story
    content = re.sub(r"^## .+\n", "", content)

    word_count = count_chinese_chars(content)

    return ChapterDraft(
        chapter_num=ch_num,
        title=title,
        content=content,
        word_count=word_count,
        status="draft",
    )
