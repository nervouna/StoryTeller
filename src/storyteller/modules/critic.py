"""Critic module (不高兴) — review chapter content and produce suggestions."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.config import Settings
from storyteller.db import repository as repo
from storyteller.db.engine import create_engine, get_session_factory
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import critic as critic_prompts
from storyteller.llm.tools import ALL_WORLD_TOOLS, handle_tool_call
from storyteller.log import get_logger
from storyteller.project.models import ProjectContext
from storyteller.utils.markdown import parse_sections

log = get_logger("critic")


@dataclass
class CriticResult:
    approved: bool
    comments: str       # 审核意见 (raw text)
    suggestions: str    # 修改建议 (numbered list as text)


async def critic_review_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int,
    content: str,
) -> CriticResult | None:
    """Review a chapter and return critique + suggestions.

    `content` is the chapter text to review (caller is responsible for loading it
    from disk or memory). The module itself is pure — no I/O beyond the LLM call
    and DB queries for world-building context.
    """
    if not ctx.outline:
        log.error("No outline available")
        ctx.errors.append("Critic: no outline")
        return None
    if not content:
        log.warning("No content for chapter %d", chapter_num)
        return None

    llm_config = settings.get_llm("critic")
    client = create_client_from_config(llm_config)

    engine = await create_engine(ctx.db_path)
    factory = get_session_factory(engine)

    ch_outline = ctx.outline.get_chapter(chapter_num)

    try:
        async with factory() as session:
            return await _review(client, session, chapter_num, content, ch_outline)
    finally:
        await engine.dispose()


async def _review(
    client: LLMClient,
    session: AsyncSession,
    ch_num: int,
    content: str,
    ch_outline,
) -> CriticResult:
    rules = await repo.get_all_world_rules(session)
    rules_text = "\n".join(f"- [{r.category}] {r.rule_text}" for r in rules) if rules else "（无世界规则）"

    char_info = "（无角色信息）"
    if ch_outline and ch_outline.characters_involved:
        char_parts = []
        for name in ch_outline.characters_involved:
            char = await repo.get_character_by_name(session, name)
            if char:
                tier = char.power_tier.value if char.power_tier else "未知"
                char_parts.append(f"- **{char.name}** [{tier}] 性格:{char.personality}")
        if char_parts:
            char_info = "\n".join(char_parts)

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

    sections = parse_sections(response)
    comments = sections.get("审核意见", "")
    suggestions = sections.get("修改建议", "")
    # Blocker-only gate: 🔴 marks severity in the prompt contract; yellow/green pass
    approved = "🔴" not in comments

    log.info(
        "Chapter %d review: approved=%s comments=%d chars suggestions=%d chars",
        ch_num, approved, len(comments), len(suggestions),
    )
    return CriticResult(approved=approved, comments=comments, suggestions=suggestions)
