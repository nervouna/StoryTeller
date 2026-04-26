"""Critic module (不高兴) — review and polish chapters."""
from __future__ import annotations

import click
from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.config import Settings
from storyteller.db import repository as repo
from storyteller.db.engine import create_engine, get_session_factory
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import critic as critic_prompts
from storyteller.llm.tools import ALL_WORLD_TOOLS, handle_tool_call
from storyteller.log import get_logger
from storyteller.project.models import ChapterDraft, ProjectContext
from storyteller.utils.chinese import count_chinese_chars
from storyteller.utils.markdown import read_chapter, write_chapter

log = get_logger("critic")


async def critic_review_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int | None = None,
    auto_accept: bool = False,
) -> ProjectContext:
    """Review and polish a chapter.

    Interactive: presents issues to human, gets approval before rewriting.
    If auto_accept=True, skips the prompt and accepts the polished version.
    """
    if not ctx.outline:
        log.error("No outline available")
        ctx.errors.append("Critic: no outline")
        return ctx

    llm_config = settings.get_llm("critic")
    client = create_client_from_config(llm_config)

    engine = await create_engine(ctx.db_path)
    factory = get_session_factory(engine)

    chapters_to_review = []
    if chapter_num:
        chapters_to_review = [chapter_num]
    else:
        # Review all draft chapters
        for draft in ctx.chapters:
            if draft.status == "draft":
                chapters_to_review.append(draft.chapter_num)
        if not chapters_to_review:
            # Try reading from disk
            from storyteller.utils.markdown import list_chapters
            chapters_to_review = [num for num, _ in list_chapters(ctx.project_dir)]

    for ch_num in chapters_to_review:
        log.info("Reviewing chapter %d...", ch_num)
        async with factory() as session:
            ctx = await _review_single_chapter(ctx, settings, client, session, ch_num, auto_accept)

    return ctx


async def _review_single_chapter(
    ctx: ProjectContext,
    settings: Settings,
    client: LLMClient,
    session: AsyncSession,
    ch_num: int,
    auto_accept: bool = False,
) -> ProjectContext:
    """Review a single chapter. If auto_accept, skip the interactive prompt."""
    # Get chapter content
    content = read_chapter(ctx.project_dir, ch_num)
    if not content:
        # Check in-memory drafts
        for draft in ctx.chapters:
            if draft.chapter_num == ch_num:
                content = draft.content
                break
    if not content:
        log.warning("No content for chapter %d", ch_num)
        return ctx

    # Get world rules for context
    rules = await repo.get_all_world_rules(session)
    rules_text = "\n".join(f"- [{r.category}] {r.rule_text}" for r in rules) if rules else "（无世界规则）"

    # Get relevant characters
    ch_outline = None
    for ch in ctx.outline.chapters:
        if ch.chapter_num == ch_num:
            ch_outline = ch
            break

    char_info = ""
    if ch_outline and ch_outline.characters_involved:
        char_parts = []
        for name in ch_outline.characters_involved:
            char = await repo.get_character_by_name(session, name)
            if char:
                tier = char.power_tier.value if char.power_tier else "未知"
                char_parts.append(f"- **{char.name}** [{tier}] 性格:{char.personality}")
        char_info = "\n".join(char_parts) if char_parts else "（无角色信息）"

    user_prompt = critic_prompts.USER.format(
        chapter_num=ch_num,
        chapter_content=content,
        world_rules=rules_text,
        character_info=char_info,
    )

    async def _tool_handler(name: str, input: dict) -> str:
        return await handle_tool_call(session, name, input)

    response = await client.call_with_tools_async(
        system=critic_prompts.SYSTEM,
        user=user_prompt,
        tools=ALL_WORLD_TOOLS,
        tool_handler=_tool_handler,
        max_rounds=3,
    )

    # Parse response
    review = _parse_review(response)

    # Show review to human
    click.echo(f"\n📋 不高兴 — 第{ch_num}章审核报告")
    click.echo("=" * 50)
    click.echo(review.get("审核意见", "（无审核意见）"))
    click.echo("\n📝 修改建议:")
    click.echo(review.get("修改建议", "（无修改建议）"))
    click.echo("=" * 50)

    # Ask for approval (or auto-accept)
    polished = review.get("润色后版本", "")
    if not polished:
        click.echo("⚠️  未生成润色版本，保留原稿")
        return ctx

    if auto_accept:
        click.echo("\n✅ 自动接受润色版本")
        final_content = polished
    else:
        choice = click.prompt(
            "\n请选择: [a]接受润色 [e]手动编辑 [s]跳过",
            type=click.Choice(["a", "e", "s"]),
            default="a",
        )

        if choice == "a":
            final_content = polished
        elif choice == "e":
            import os
            import tempfile
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                    f.write(polished)
                    tmp_path = f.name
                click.echo(f"请编辑文件: {tmp_path}")
                click.echo("编辑完成后按回车继续...")
                input()
                with open(tmp_path, encoding="utf-8") as f:
                    final_content = f.read()
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        else:
            click.echo("跳过润色，保留原稿")
            return ctx

    # Update draft
    word_count = count_chinese_chars(final_content)
    updated = False
    for draft in ctx.chapters:
        if draft.chapter_num == ch_num:
            draft.content = final_content
            draft.word_count = word_count
            draft.status = "reviewed"
            draft.critic_notes = review.get("审核意见", "")
            updated = True
            break

    if not updated:
        ctx.chapters.append(ChapterDraft(
            chapter_num=ch_num,
            title=ch_outline.title if ch_outline else "",
            content=final_content,
            word_count=word_count,
            status="reviewed",
            critic_notes=review.get("审核意见", ""),
        ))

    # Save to disk
    title = ch_outline.title if ch_outline else ""
    write_chapter(ctx.project_dir, ch_num, title, final_content)
    log.info("Chapter %d reviewed and saved: %d chars", ch_num, word_count)

    return ctx


def _parse_review(text: str) -> dict[str, str]:
    """Parse critic response into sections."""
    from storyteller.utils.markdown import parse_sections
    return parse_sections(text)
