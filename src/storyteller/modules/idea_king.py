"""Idea King module (点子王) — interactive outline co-creation."""
from __future__ import annotations

import re
from pathlib import Path

import click

from storyteller.config import Settings
from storyteller.llm.client import LLMClient, create_client_from_config
from storyteller.llm.prompts import idea_king as idea_king_prompts
from storyteller.log import get_logger
from storyteller.project.models import ChapterOutline, Outline, ProjectContext
from storyteller.utils.markdown import write_outline

log = get_logger("idea_king")


async def idea_king_interactive(ctx: ProjectContext, settings: Settings) -> ProjectContext:
    """Interactive outline discussion with human via CLI."""
    log.info("Starting Idea King session...")

    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    # Load telescope data if available
    trends = ""
    telescope_path = ctx.project_dir / "telescope.md"
    if telescope_path.exists():
        trends = telescope_path.read_text(encoding="utf-8")
    elif ctx.telescope and ctx.telescope.raw_data:
        trends = ctx.telescope.raw_data

    # Build initial prompt
    if trends:
        system_prompt = idea_king_prompts.SYSTEM
        user_prompt = idea_king_prompts.USER_TREND.format(trends=trends[:3000])
    else:
        system_prompt = idea_king_prompts.SYSTEM
        user_prompt = "没有市场趋势数据。请直接问我想要写什么类型的小说，然后我们一起讨论大纲。"

    click.echo("\n🖊️  点子王：让我们一起构思一部小说！")
    click.echo("   （输入 'done' 结束讨论，'save' 保存当前进度）\n")

    history: list[dict[str, str]] = []

    # First LLM response
    llm_response = client.call(system=system_prompt, user=user_prompt)
    click.echo(f"💡 点子王：{llm_response}\n")
    history.append({"role": "assistant", "content": llm_response})

    # Interactive loop
    while True:
        user_input = click.prompt("你", type=str, default="", show_default=False)
        if not user_input.strip():
            continue

        if user_input.strip().lower() == "done":
            click.echo("\n正在生成最终大纲...")
            break

        if user_input.strip().lower() == "save":
            _save_progress(ctx, history, client, system_prompt)
            click.echo("✅ 进度已保存，继续讨论...\n")
            continue

        history.append({"role": "user", "content": user_input})

        # Build conversation context
        history_text = "\n".join(
            f"{'我' if h['role'] == 'user' else '点子王'}: {h['content']}"
            for h in history[-10:]  # Last 10 turns
        )

        response = client.call(
            system=system_prompt,
            user=idea_king_prompts.USER_OUTLINE.format(history=history_text),
        )
        click.echo(f"\n💡 点子王：{response}\n")
        history.append({"role": "assistant", "content": response})

    # Generate final outline as JSON
    history_text = "\n".join(
        f"{'我' if h['role'] == 'user' else '点子王'}: {h['content']}"
        for h in history
    )
    data = client.call_json(
        system=system_prompt + "\n\n现在请根据讨论内容，输出最终的完整大纲。以 JSON 格式输出。",
        user=f"讨论历史：\n{history_text}\n\n请输出最终大纲。",
    )

    # Parse and save
    outline = _parse_outline_data(data)
    ctx.outline = outline

    # Save outline.md
    outline_md = _outline_to_markdown(outline)
    write_outline(ctx.project_dir, outline_md)
    log.info("Outline saved to %s", ctx.project_dir / "outline.md")

    click.echo(f"\n✅ 大纲已保存！共 {len(outline.chapters)} 章")
    return ctx


async def idea_king_auto(
    ctx: ProjectContext,
    settings: Settings,
    genre: str = "",
    premise: str = "",
) -> ProjectContext:
    """Generate outline automatically without human interaction."""
    log.info("Starting auto outline generation...")

    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    # Load telescope data
    trends = ""
    telescope_path = ctx.project_dir / "telescope.md"
    if telescope_path.exists():
        trends = telescope_path.read_text(encoding="utf-8")

    prompt_parts = []
    if trends:
        prompt_parts.append(f"市场趋势：\n{trends[:2000]}")
    if genre:
        prompt_parts.append(f"小说类型：{genre}")
    if premise:
        prompt_parts.append(f"故事前提：{premise}")
    prompt_parts.append("请生成一个完整的小说大纲，包含10-20章的详细规划。")

    user_prompt = "\n\n".join(prompt_parts)

    data = client.call_json(
        system=idea_king_prompts.SYSTEM + "\n\n不需要讨论，直接生成完整大纲。以 JSON 格式输出。",
        user=user_prompt,
    )

    outline = _parse_outline_data(data)
    ctx.outline = outline

    outline_md = _outline_to_markdown(outline)
    write_outline(ctx.project_dir, outline_md)
    log.info("Auto outline saved: %d chapters", len(outline.chapters))

    return ctx


async def idea_king_extend(
    ctx: ProjectContext,
    settings: Settings,
    target_chapter: int,
) -> ProjectContext:
    """Extend outline until the last chapter reaches target_chapter number.

    Generates new chapter outlines from the last existing chapter up to
    target_chapter, saves to disk, and returns updated context.
    """
    if not ctx.outline:
        raise ValueError("No outline to extend")

    last_chapter_num = max(ch.chapter_num for ch in ctx.outline.chapters)
    num_needed = target_chapter - last_chapter_num

    if num_needed <= 0:
        log.info("Outline already reaches chapter %d, target %d — no extension needed",
                 last_chapter_num, target_chapter)
        return ctx

    log.info("Extending outline: chapter %d → %d", last_chapter_num, target_chapter)

    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    outline_text = _outline_to_markdown(ctx.outline)

    system_prompt = idea_king_prompts.EXTEND_SYSTEM.format(num_chapters=num_needed)
    user_prompt = idea_king_prompts.EXTEND_USER.format(
        outline_text=outline_text,
        next_chapter_num=last_chapter_num + 1,
        num_chapters=num_needed,
    )

    data = client.call_json(system=system_prompt, user=user_prompt)

    # Reuse existing parser, then filter out overlapping chapters
    parsed = _parse_outline_data(data)
    seen: set[int] = set()
    new_chapters: list[ChapterOutline] = []
    for ch in parsed.chapters:
        if ch.chapter_num <= last_chapter_num or ch.chapter_num in seen:
            continue
        seen.add(ch.chapter_num)
        new_chapters.append(ch)

    ctx.outline.chapters.extend(new_chapters)
    ctx.outline.chapters.sort(key=lambda c: c.chapter_num)
    log.info("Added %d new chapters (total: %d)", len(new_chapters), len(ctx.outline.chapters))

    outline_md = _outline_to_markdown(ctx.outline)
    write_outline(ctx.project_dir, outline_md)

    return ctx


# ---------- JSON Schema for structured output ----------

OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "小说标题"},
        "genre": {"type": "string", "description": "小说类型"},
        "logline": {"type": "string", "description": "一句话概括"},
        "themes": {"type": "array", "items": {"type": "string"}, "description": "核心主题列表"},
        "target_audience": {"type": "string", "description": "目标读者"},
        "notes": {"type": "string", "description": "世界观概述"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chapter_num": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string", "description": "本章摘要100-200字"},
                    "key_events": {"type": "array", "items": {"type": "string"}},
                    "characters_involved": {"type": "array", "items": {"type": "string"}},
                    "setting": {"type": "string"},
                },
                "required": ["chapter_num", "title", "summary"],
            },
        },
    },
    "required": ["title", "genre", "logline", "chapters"],
    "additionalProperties": False,
}


# ---------- Load from disk ----------

def load_outline_from_file(project_dir: Path) -> Outline | None:
    """Load outline from outline.md, parsing the structured markdown."""
    outline_path = project_dir / "outline.md"
    if not outline_path.exists():
        return None
    text = outline_path.read_text(encoding="utf-8")
    if not text.strip() or text.strip().startswith("<!--"):
        return None

    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            else:
                sections[""] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        elif line.startswith("# ") and not current_key:
            continue
        else:
            current_lines.append(line)
    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()
    elif current_lines:
        sections[""] = "\n".join(current_lines).strip()

    # Parse header fields
    header = sections.pop("", "")  # Lines before first ##
    title = ""
    for line in text.split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
            break

    genre = ""
    logline = ""
    themes: list[str] = []
    target_audience = ""

    for line in header.split("\n"):
        line = line.strip().lstrip("- ")
        if line.startswith("**类型**:"):
            genre = line.split(":", 1)[1].strip()
        elif line.startswith("**一句话概括**:"):
            logline = line.split(":", 1)[1].strip()
        elif line.startswith("**核心主题**:"):
            themes = [t.strip() for t in line.split(":", 1)[1].split(",")]
        elif line.startswith("**目标读者**:"):
            target_audience = line.split(":", 1)[1].strip()

    notes = sections.get("世界观概述", "")

    # Parse chapters
    chapters: list[ChapterOutline] = []
    chapters_text = sections.get("章节大纲", "")
    heading_re = re.compile(r"### 第(\d+)章 - (.+)")
    for match in heading_re.finditer(chapters_text):
        ch_num = int(match.group(1))
        ch_title = match.group(2).strip()
        # Get body until next heading
        body_start = match.end()
        next_match = heading_re.search(chapters_text, body_start)
        body_end = next_match.start() if next_match else len(chapters_text)
        body = chapters_text[body_start:body_end].strip()

        summary = ""
        key_events: list[str] = []
        characters: list[str] = []
        setting = ""

        for bline in body.split("\n"):
            bline = bline.strip()
            # Strip markdown bold: **xxx** → xxx
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", bline)
            if clean.startswith("摘要:"):
                summary = clean.split(":", 1)[1].strip()
            elif clean.startswith("关键事件:"):
                key_events = [e.strip() for e in clean.split(":", 1)[1].split(",")]
            elif clean.startswith("出场人物:"):
                characters = [c.strip() for c in clean.split(":", 1)[1].split(",")]
            elif clean.startswith("地点:"):
                setting = clean.split(":", 1)[1].strip()

        chapters.append(ChapterOutline(
            chapter_num=ch_num,
            title=ch_title,
            summary=summary,
            key_events=key_events,
            characters_involved=characters,
            setting=setting,
        ))

    if not title and not chapters:
        return None

    return Outline(
        title=title,
        genre=genre,
        logline=logline,
        themes=themes,
        target_audience=target_audience,
        notes=notes,
        chapters=chapters,
    )


# ---------- Parsing ----------

def _parse_outline_data(data: dict) -> Outline:
    """Parse structured dict into Outline model."""
    chapters = [
        ChapterOutline(
            chapter_num=ch.get("chapter_num", i + 1),
            title=ch.get("title", ""),
            summary=ch.get("summary", ""),
            key_events=ch.get("key_events", []),
            characters_involved=ch.get("characters_involved", []),
            setting=ch.get("setting", ""),
        )
        for i, ch in enumerate(data.get("chapters", []))
    ]

    return Outline(
        title=data.get("title", ""),
        genre=data.get("genre", ""),
        logline=data.get("logline", ""),
        themes=data.get("themes", []),
        target_audience=data.get("target_audience", ""),
        notes=data.get("notes", ""),
        chapters=chapters,
    )


def _save_progress(ctx: ProjectContext, history: list, client: LLMClient, system: str) -> None:
    """Save current discussion progress."""
    history_text = "\n".join(
        f"{'我' if h['role'] == 'user' else '点子王'}: {h['content']}"
        for h in history
    )
    partial = client.call(
        system=system + "\n\n输出当前讨论进展的大纲草稿，标注哪些部分还需要讨论。",
        user=f"讨论历史：\n{history_text}",
    )
    progress_path = ctx.project_dir / "outline_progress.md"
    progress_path.write_text(partial, encoding="utf-8")


def _outline_to_markdown(outline: Outline) -> str:
    """Convert Outline to markdown."""
    lines = [f"# {outline.title}", ""]
    lines.append(f"- **类型**: {outline.genre}")
    lines.append(f"- **一句话概括**: {outline.logline}")
    if outline.themes:
        lines.append(f"- **核心主题**: {', '.join(outline.themes)}")
    lines.append(f"- **目标读者**: {outline.target_audience}")
    lines.append("")

    if outline.notes:
        lines.append("## 世界观概述")
        lines.append(outline.notes)
        lines.append("")

    if outline.chapters:
        lines.append("## 章节大纲")
        lines.append("")
        for ch in outline.chapters:
            lines.append(f"### 第{ch.chapter_num}章 - {ch.title}")
            if ch.summary:
                lines.append(f"**摘要**: {ch.summary}")
            if ch.key_events:
                lines.append(f"**关键事件**: {', '.join(ch.key_events)}")
            if ch.characters_involved:
                lines.append(f"**出场人物**: {', '.join(ch.characters_involved)}")
            if ch.setting:
                lines.append(f"**地点**: {ch.setting}")
            lines.append("")

    return "\n".join(lines)
