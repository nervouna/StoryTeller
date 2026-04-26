"""SQLAlchemy 2.0 ORM models for world-building settings."""
from __future__ import annotations

import datetime
import enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ---------- Enums ----------

class PowerTier(enum.StrEnum):
    MORTAL = "凡人"
    QI_REFINING = "炼气"
    FOUNDATION = "筑基"
    CORE = "金丹"
    NASCENT_SOUL = "元婴"
    SPIRIT_SEVERING = "化神"
    VOID_REFINING = "炼虚"
    BODY_INTEGRATION = "合体"
    MAHAYANA = "大乘"
    TRIBULATION = "渡劫"


# ---------- Association Tables ----------

character_faction = Table(
    "character_faction",
    Base.metadata,
    Column("character_id", Integer, ForeignKey("characters.id"), primary_key=True),
    Column("faction_id", Integer, ForeignKey("factions.id"), primary_key=True),
)

character_item = Table(
    "character_item",
    Base.metadata,
    Column("character_id", Integer, ForeignKey("characters.id"), primary_key=True),
    Column("item_id", Integer, ForeignKey("items.id"), primary_key=True),
)


# ---------- Core Tables ----------

class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    title = Column(String(200), default="")
    alias = Column(String(200), default="")
    age = Column(Integer, nullable=True)
    gender = Column(String(20), default="")
    power_level = Column(String(50), default="")
    power_tier = Column(SAEnum(PowerTier), nullable=True)
    backstory = Column(Text, default="")
    personality = Column(Text, default="")
    appearance = Column(Text, default="")
    goals = Column(Text, default="")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    factions = relationship("Faction", secondary=character_faction, back_populates="members")
    items = relationship("Item", secondary=character_item, back_populates="owners")
    relationships = relationship(
        "CharacterRelationship",
        foreign_keys="CharacterRelationship.character_id",
        back_populates="character",
    )


class Faction(Base):
    __tablename__ = "factions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, default="")
    power_level = Column(String(50), default="")
    territory = Column(String(200), default="")
    philosophy = Column(Text, default="")
    leader_id = Column(Integer, ForeignKey("characters.id"), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.now)

    members = relationship("Character", secondary=character_faction, back_populates="factions")
    leader = relationship("Character", foreign_keys=[leader_id])


class WorldRegion(Base):
    __tablename__ = "world_regions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("world_regions.id"), nullable=True)
    region_type = Column(String(50), default="")
    description = Column(Text, default="")
    rules = Column(Text, default="")
    notable_features = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.now)

    parent = relationship("WorldRegion", remote_side=[id])


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)
    item_type = Column(String(50), default="")
    power_level = Column(String(50), default="")
    description = Column(Text, default="")
    origin = Column(String(200), default="")
    special_abilities = Column(Text, default="")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.now)

    owners = relationship("Character", secondary=character_item, back_populates="items")


class PowerSystem(Base):
    __tablename__ = "power_system"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier_name = Column(String(50), unique=True, nullable=False)
    tier_order = Column(Integer, nullable=False)
    description = Column(Text, default="")
    typical_abilities = Column(Text, default="")
    notes = Column(Text, default="")


class Economy(Base):
    __tablename__ = "economy"

    id = Column(Integer, primary_key=True, autoincrement=True)
    currency_name = Column(String(50), nullable=False)
    tier = Column(String(50), default="")
    exchange_rate = Column(Float, default=1.0)
    description = Column(Text, default="")
    notes = Column(Text, default="")


class WorldRule(Base):
    __tablename__ = "world_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
    rule_text = Column(Text, nullable=False)
    source = Column(String(100), default="")
    priority = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.now)


class CharacterRelationship(Base):
    __tablename__ = "character_relationships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    character_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("characters.id"), nullable=False)
    rel_type = Column(String(50), nullable=False)
    description = Column(Text, default="")

    character = relationship("Character", foreign_keys=[character_id], back_populates="relationships")
    target = relationship("Character", foreign_keys=[target_id])
