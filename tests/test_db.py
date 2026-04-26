"""Tests for database operations."""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from storyteller.db import repository as repo
from storyteller.db.models import Base, Character, Faction, PowerTier, WorldRule


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    yield session
    await session.close()
    await engine.dispose()


@pytest.mark.asyncio
async def test_add_and_query_character(db_session: AsyncSession):
    char = Character(name="林远", power_tier=PowerTier.MORTAL, personality="沉稳")
    db_session.add(char)
    await db_session.commit()

    result = await repo.get_character_by_name(db_session, "林远")
    assert result is not None
    assert result.name == "林远"
    assert result.power_tier == PowerTier.MORTAL


@pytest.mark.asyncio
async def test_character_not_found(db_session: AsyncSession):
    result = await repo.get_character_by_name(db_session, "不存在")
    assert result is None


@pytest.mark.asyncio
async def test_add_faction_with_members(db_session: AsyncSession):
    char = Character(name="掌门", power_tier=PowerTier.CORE)
    faction = Faction(name="天剑宗", description="剑修圣地")
    faction.members.append(char)
    db_session.add_all([char, faction])
    await db_session.commit()

    result = await repo.find_characters_by_faction(db_session, "天剑宗")
    assert len(result) == 1
    assert result[0].name == "掌门"


@pytest.mark.asyncio
async def test_world_rules(db_session: AsyncSession):
    db_session.add(WorldRule(category="战力", rule_text="金丹不可对凡人出手", priority=10))
    db_session.add(WorldRule(category="地理", rule_text="禁地不可进入", priority=5))
    await db_session.commit()

    rules = await repo.get_all_world_rules(db_session)
    assert len(rules) == 2
    assert rules[0].priority >= rules[1].priority  # ordered by priority desc


@pytest.mark.asyncio
async def test_get_all_characters_empty(db_session: AsyncSession):
    result = await repo.get_all_characters(db_session)
    assert result == []
