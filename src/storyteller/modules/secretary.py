"""Secretary module (秘书长) — world-building DB management.

Responsibilities:
1. Sync: parse outline → INSERT characters/factions/items into DB
2. Query: provide world context to Writer/Critic
3. Interactive: CLI for manual edits
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.config import Settings
from storyteller.db import repository as repo
from storyteller.db.engine import create_engine, get_session_factory
from storyteller.db.models import (
    Character,
    Faction,
    Item,
    PowerSystem,
    PowerTier,
    WorldRegion,
    WorldRule,
)
from storyteller.llm.client import create_client_from_config
from storyteller.llm.prompts import secretary as secretary_prompts
from storyteller.log import get_logger
from storyteller.project.models import Outline, ProjectContext

log = get_logger("secretary")

# Map common tier names to PowerTier enum
_TIER_MAP = {
    "凡人": PowerTier.MORTAL,
    "炼气": PowerTier.QI_REFINING,
    "筑基": PowerTier.FOUNDATION,
    "金丹": PowerTier.CORE,
    "元婴": PowerTier.NASCENT_SOUL,
    "化神": PowerTier.SPIRIT_SEVERING,
    "炼虚": PowerTier.VOID_REFINING,
    "合体": PowerTier.BODY_INTEGRATION,
    "大乘": PowerTier.MAHAYANA,
    "渡劫": PowerTier.TRIBULATION,
}


def _parse_tier(value: str) -> PowerTier | None:
    """Best-effort parse of a tier string into PowerTier."""
    if not value:
        return None
    for key, tier in _TIER_MAP.items():
        if key in value:
            return tier
    return None


async def secretary_sync(ctx: ProjectContext, settings: Settings) -> ProjectContext:
    """Extract world-building data from outline and populate DB.

    Uses LLM to parse the outline into structured data, then inserts into SQLite.
    """
    if not ctx.outline:
        log.warning("No outline to sync from")
        return ctx

    outline_text = _outline_to_text(ctx.outline)
    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    log.info("Extracting world-building data from outline...")
    raw = client.call(
        system=secretary_prompts.SYSTEM,
        user=secretary_prompts.USER.format(outline=outline_text),
    )

    # Parse JSON from response
    data = _extract_json(raw)
    if not data:
        log.error("Failed to parse JSON from LLM response")
        ctx.errors.append("Secretary: failed to extract settings from outline")
        return ctx

    # Populate DB
    engine = await create_engine(ctx.db_path)
    factory = get_session_factory(engine)
    async with factory() as session:
        await _populate_db(session, data)
        await session.commit()

    log.info("World-building DB populated successfully")
    return ctx


async def secretary_query(session: AsyncSession, query: str) -> str:
    """Natural language query against the world-building DB.

    Returns a formatted string response.
    """
    # Simple keyword-based routing for MVP
    query.lower()

    if "角色" in query or "人物" in query:
        chars = await repo.get_all_characters(session)
        return _format_characters(chars)

    if "势力" in query or "宗门" in query or "门派" in query:
        factions = await repo.get_all_factions(session)
        return _format_factions(factions)

    if "规则" in query or "设定" in query:
        rules = await repo.get_all_world_rules(session)
        return _format_rules(rules)

    if "道具" in query or "法宝" in query or "丹药" in query:
        items = await repo.get_all_items(session)
        return _format_items(items)

    if "境界" in query or "等级" in query or "修炼" in query:
        tiers = await repo.get_power_system(session)
        return _format_power_system(tiers)

    if "区域" in query or "地图" in query:
        regions = await repo.get_all_regions(session)
        return _format_regions(regions)

    # Default: dump everything
    return await secretary_dump(session)


async def secretary_dump(session: AsyncSession) -> str:
    """Dump all world-building data as formatted text."""
    parts = []
    chars = await repo.get_all_characters(session)
    if chars:
        parts.append(_format_characters(chars))

    factions = await repo.get_all_factions(session)
    if factions:
        parts.append(_format_factions(factions))

    rules = await repo.get_all_world_rules(session)
    if rules:
        parts.append(_format_rules(rules))

    items = await repo.get_all_items(session)
    if items:
        parts.append(_format_items(items))

    tiers = await repo.get_power_system(session)
    if tiers:
        parts.append(_format_power_system(tiers))

    regions = await repo.get_all_regions(session)
    if regions:
        parts.append(_format_regions(regions))

    return "\n\n".join(parts) if parts else "（数据库为空）"


# ---------- Internal helpers ----------

def _outline_to_text(outline: Outline) -> str:
    parts = [f"标题: {outline.title}"]
    parts.append(f"类型: {outline.genre}")
    parts.append(f"一句话概括: {outline.logline}")
    if outline.themes:
        parts.append(f"主题: {', '.join(outline.themes)}")
    parts.append(f"目标读者: {outline.target_audience}")
    parts.append("\n章节大纲:")
    for ch in outline.chapters:
        parts.append(f"\n第{ch.chapter_num}章 - {ch.title}")
        parts.append(f"  摘要: {ch.summary}")
        if ch.key_events:
            parts.append(f"  关键事件: {', '.join(ch.key_events)}")
        if ch.characters_involved:
            parts.append(f"  出场人物: {', '.join(ch.characters_involved)}")
        if ch.setting:
            parts.append(f"  地点: {ch.setting}")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response. Returns None on failure."""
    from storyteller.llm.client import _extract_json as _do_extract
    try:
        return _do_extract(text)
    except ValueError:
        return None


async def _populate_db(session: AsyncSession, data: dict[str, Any]) -> None:
    """Insert extracted data into DB. Clears existing data first (full sync)."""
    from sqlalchemy import text
    for table in [
        "character_relationships", "character_item", "character_faction",
        "world_rules", "economy", "power_system", "items",
        "world_regions", "factions", "characters",
    ]:
        await session.execute(text(f"DELETE FROM {table}"))

    # Characters
    name_to_char: dict[str, Character] = {}
    for c_data in data.get("characters", []):
        char = Character(
            name=c_data.get("name", ""),
            title=c_data.get("title", ""),
            alias=c_data.get("alias", ""),
            age=c_data.get("age"),
            gender=c_data.get("gender", ""),
            power_tier=_parse_tier(c_data.get("power_tier", "")),
            personality=c_data.get("personality", ""),
            appearance=c_data.get("appearance", ""),
            goals=c_data.get("goals", ""),
            backstory=c_data.get("backstory", ""),
        )
        session.add(char)
        await session.flush()
        name_to_char[char.name] = char

    # Factions
    name_to_faction: dict[str, Faction] = {}
    for f_data in data.get("factions", []):
        faction = Faction(
            name=f_data.get("name", ""),
            description=f_data.get("description", ""),
            power_level=f_data.get("power_level", ""),
            territory=f_data.get("territory", ""),
            philosophy=f_data.get("philosophy", ""),
        )
        # Link leader
        leader_name = f_data.get("leader_name", "")
        if leader_name and leader_name in name_to_char:
            faction.leader_id = name_to_char[leader_name].id
        session.add(faction)
        await session.flush()
        name_to_faction[faction.name] = faction

    # Link characters to factions
    for c_data in data.get("characters", []):
        char_name = c_data.get("name", "")
        if char_name not in name_to_char:
            continue
        char = name_to_char[char_name]
        # Check if faction membership is mentioned in character data
        # (We rely on the LLM to include faction info in the character data)

    # Items
    for i_data in data.get("items", []):
        item = Item(
            name=i_data.get("name", ""),
            item_type=i_data.get("item_type", ""),
            power_level=i_data.get("power_level", ""),
            description=i_data.get("description", ""),
            special_abilities=i_data.get("special_abilities", ""),
        )
        session.add(item)

    # World Rules
    for r_data in data.get("world_rules", []):
        rule = WorldRule(
            category=r_data.get("category", "通用"),
            rule_text=r_data.get("rule_text", ""),
            priority=r_data.get("priority", 0),
        )
        session.add(rule)

    # Regions
    for r_data in data.get("regions", []):
        region = WorldRegion(
            name=r_data.get("name", ""),
            region_type=r_data.get("region_type", ""),
            description=r_data.get("description", ""),
        )
        session.add(region)

    # Power System
    for p_data in data.get("power_system", []):
        tier = PowerSystem(
            tier_name=p_data.get("tier_name", ""),
            tier_order=p_data.get("tier_order", 0),
            description=p_data.get("description", ""),
            typical_abilities=p_data.get("typical_abilities", ""),
        )
        session.add(tier)

    await session.flush()


# ---------- Formatters ----------

def _format_characters(chars: list) -> str:
    lines = ["## 角色列表"]
    for c in chars:
        tier = c.power_tier.value if c.power_tier else "未知"
        factions = ", ".join(f.name for f in c.factions) if c.factions else "无"
        lines.append(f"- **{c.name}** [{tier}] 势力:{factions}")
        if c.personality:
            lines.append(f"  性格: {c.personality}")
        if c.goals:
            lines.append(f"  目标: {c.goals}")
    return "\n".join(lines)


def _format_factions(factions: list) -> str:
    lines = ["## 势力列表"]
    for f in factions:
        leader = f.leader.name if f.leader else "未知"
        members = ", ".join(m.name for m in f.members) if f.members else "无"
        lines.append(f"- **{f.name}** 领袖:{leader} 成员:{members}")
        if f.description:
            lines.append(f"  {f.description}")
    return "\n".join(lines)


def _format_rules(rules: list) -> str:
    lines = ["## 世界规则"]
    for r in rules:
        lines.append(f"- [{r.category}] {r.rule_text}")
    return "\n".join(lines)


def _format_items(items: list) -> str:
    lines = ["## 道具列表"]
    for i in items:
        lines.append(f"- **{i.name}** ({i.item_type}) {i.description}")
    return "\n".join(lines)


def _format_power_system(tiers: list) -> str:
    lines = ["## 修炼体系"]
    for t in sorted(tiers, key=lambda x: x.tier_order):
        lines.append(f"{t.tier_order}. **{t.tier_name}** — {t.description}")
    return "\n".join(lines)


def _format_regions(regions: list) -> str:
    lines = ["## 世界区域"]
    for r in regions:
        lines.append(f"- **{r.name}** ({r.region_type}) {r.description}")
    return "\n".join(lines)
