"""LLM tool definitions and handlers for tool-use calls.

Tools are defined in Anthropic API format and dispatched via handle_tool_call().
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from storyteller.db import repository as repo
from storyteller.log import get_logger

log = get_logger("tools")

# ---------- Tool Definitions (Anthropic format) ----------

QUERY_CHARACTERS_TOOL = {
    "name": "query_characters",
    "description": "查询角色信息。可按名字查询单个角色，或查询某个势力的所有成员。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "角色名字（精确匹配）"},
            "faction": {"type": "string", "description": "势力名字，查询该势力所有成员"},
        },
    },
}

QUERY_FACTIONS_TOOL = {
    "name": "query_factions",
    "description": "查询势力/组织信息。不传参数返回所有势力。",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "势力名字（精确匹配）"},
        },
    },
}

QUERY_WORLD_RULES_TOOL = {
    "name": "query_world_rules",
    "description": "查询世界规则。可按分类过滤（战力/地理/经济/禁忌等）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "规则分类"},
        },
    },
}

QUERY_ITEMS_TOOL = {
    "name": "query_items",
    "description": "查询道具/法宝/丹药信息。可按类型过滤。",
    "input_schema": {
        "type": "object",
        "properties": {
            "item_type": {"type": "string", "description": "道具类型（法宝/丹药/功法等）"},
        },
    },
}

QUERY_POWER_SYSTEM_TOOL = {
    "name": "query_power_system",
    "description": "查询力量/修炼体系的等级信息。",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

QUERY_RELATIONSHIPS_TOOL = {
    "name": "query_relationships",
    "description": "查询角色之间的关系（师徒/敌对/恋人/兄弟等）。",
    "input_schema": {
        "type": "object",
        "properties": {
            "character_name": {"type": "string", "description": "角色名字"},
        },
        "required": ["character_name"],
    },
}

QUERY_REGIONS_TOOL = {
    "name": "query_regions",
    "description": "查询世界地图区域信息。",
    "input_schema": {
        "type": "object",
        "properties": {
            "region_type": {"type": "string", "description": "区域类型（宗门/城池/秘境/大陆）"},
        },
    },
}

# All tools for writer/critic
ALL_WORLD_TOOLS = [
    QUERY_CHARACTERS_TOOL,
    QUERY_FACTIONS_TOOL,
    QUERY_WORLD_RULES_TOOL,
    QUERY_ITEMS_TOOL,
    QUERY_POWER_SYSTEM_TOOL,
    QUERY_RELATIONSHIPS_TOOL,
    QUERY_REGIONS_TOOL,
]


async def handle_tool_call(
    session: AsyncSession,
    tool_name: str,
    tool_input: dict[str, Any],
) -> str:
    """Dispatch a tool call and return the result as a string."""
    try:
        if tool_name == "query_characters":
            if "name" in tool_input and tool_input["name"]:
                char = await repo.get_character_by_name(session, tool_input["name"])
                if char:
                    return json.dumps(_serialize_character(char), ensure_ascii=False)
                return f"未找到角色: {tool_input['name']}"
            if "faction" in tool_input and tool_input["faction"]:
                chars = await repo.find_characters_by_faction(session, tool_input["faction"])
                return json.dumps([_serialize_character(c) for c in chars], ensure_ascii=False)
            chars = await repo.get_all_characters(session)
            return json.dumps([_serialize_character(c) for c in chars], ensure_ascii=False)

        elif tool_name == "query_factions":
            if "name" in tool_input and tool_input["name"]:
                factions = await repo.get_all_factions(session)
                found = [f for f in factions if f.name == tool_input["name"]]
                if found:
                    return json.dumps(_serialize_faction(found[0]), ensure_ascii=False)
                return f"未找到势力: {tool_input['name']}"
            factions = await repo.get_all_factions(session)
            return json.dumps([_serialize_faction(f) for f in factions], ensure_ascii=False)

        elif tool_name == "query_world_rules":
            rules = await repo.get_all_world_rules(session)
            if "category" in tool_input and tool_input["category"]:
                rules = [r for r in rules if r.category == tool_input["category"]]
            return json.dumps(
                [{"category": r.category, "rule": r.rule_text, "priority": r.priority} for r in rules],
                ensure_ascii=False,
            )

        elif tool_name == "query_items":
            if "item_type" in tool_input and tool_input["item_type"]:
                items = await repo.find_items_by_type(session, tool_input["item_type"])
            else:
                items = await repo.get_all_items(session)
            return json.dumps(
                [{"name": i.name, "type": i.item_type, "level": i.power_level, "desc": i.description} for i in items],
                ensure_ascii=False,
            )

        elif tool_name == "query_power_system":
            tiers = await repo.get_power_system(session)
            return json.dumps(
                [{"name": t.tier_name, "order": t.tier_order, "desc": t.description} for t in tiers],
                ensure_ascii=False,
            )

        elif tool_name == "query_relationships":
            name = tool_input.get("character_name", "")
            rels = await repo.get_character_relationships(session, name)
            return json.dumps(rels, ensure_ascii=False)

        elif tool_name == "query_regions":
            regions = await repo.get_all_regions(session)
            if "region_type" in tool_input and tool_input["region_type"]:
                regions = [r for r in regions if r.region_type == tool_input["region_type"]]
            return json.dumps(
                [{"name": r.name, "type": r.region_type, "desc": r.description} for r in regions],
                ensure_ascii=False,
            )

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        log.error("Tool %s failed: %s", tool_name, e, exc_info=True)
        return f"Error: {e}"


def _serialize_character(c) -> dict:
    return {
        "name": c.name,
        "title": c.title,
        "alias": c.alias,
        "age": c.age,
        "gender": c.gender,
        "power_tier": c.power_tier.value if c.power_tier else "",
        "personality": c.personality,
        "appearance": c.appearance,
        "goals": c.goals,
        "backstory": c.backstory,
        "factions": [f.name for f in c.factions] if c.factions else [],
        "items": [i.name for i in c.items] if c.items else [],
        "is_active": c.is_active,
    }


def _serialize_faction(f) -> dict:
    return {
        "name": f.name,
        "description": f.description,
        "power_level": f.power_level,
        "territory": f.territory,
        "philosophy": f.philosophy,
        "leader": f.leader.name if f.leader else "",
        "members": [m.name for m in f.members] if f.members else [],
    }
