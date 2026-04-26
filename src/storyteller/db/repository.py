"""High-level query helpers for the world-building DB."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from storyteller.db.models import (
    Character,
    CharacterRelationship,
    Economy,
    Faction,
    Item,
    PowerSystem,
    WorldRegion,
    WorldRule,
)


async def get_character_by_name(session: AsyncSession, name: str) -> Character | None:
    stmt = select(Character).where(Character.name == name).options(
        selectinload(Character.factions),
        selectinload(Character.items),
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def find_characters_by_faction(session: AsyncSession, faction_name: str) -> list[Character]:
    stmt = (
        select(Character)
        .join(Character.factions)
        .where(Faction.name == faction_name)
        .options(selectinload(Character.factions))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_power_ranking(session: AsyncSession) -> list[dict]:
    stmt = select(Character).order_by(Character.power_tier.desc(), Character.name)
    result = await session.execute(stmt)
    chars = result.scalars().all()
    return [
        {"name": c.name, "tier": c.power_tier.value if c.power_tier else "未知"}
        for c in chars
    ]


async def find_items_by_type(session: AsyncSession, item_type: str) -> list[Item]:
    stmt = select(Item).where(Item.item_type == item_type)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_world_rules(session: AsyncSession) -> list[WorldRule]:
    stmt = select(WorldRule).order_by(WorldRule.priority.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_character_relationships(session: AsyncSession, character_name: str) -> list[dict]:
    stmt = (
        select(CharacterRelationship)
        .join(Character, CharacterRelationship.character_id == Character.id)
        .where(Character.name == character_name)
    )
    result = await session.execute(stmt)
    rels = result.scalars().all()

    out = []
    for r in rels:
        target = await session.get(Character, r.target_id)
        out.append({
            "target": target.name if target else f"#{r.target_id}",
            "type": r.rel_type,
            "description": r.description,
        })
    return out


async def get_all_factions(session: AsyncSession) -> list[Faction]:
    stmt = select(Faction).options(selectinload(Faction.members))
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_characters(session: AsyncSession) -> list[Character]:
    stmt = select(Character).options(
        selectinload(Character.factions),
        selectinload(Character.items),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_items(session: AsyncSession) -> list[Item]:
    stmt = select(Item)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_all_regions(session: AsyncSession) -> list[WorldRegion]:
    stmt = select(WorldRegion)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_power_system(session: AsyncSession) -> list[PowerSystem]:
    stmt = select(PowerSystem).order_by(PowerSystem.tier_order)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_economy(session: AsyncSession) -> list[Economy]:
    stmt = select(Economy)
    result = await session.execute(stmt)
    return list(result.scalars().all())
