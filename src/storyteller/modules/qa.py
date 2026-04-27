"""QA module (质检员) — check chapter length/format and produce suggestions."""
from __future__ import annotations

from dataclasses import dataclass

from storyteller.config import Settings
from storyteller.llm.client import create_client_from_config
from storyteller.llm.prompts import qa as qa_prompts
from storyteller.log import get_logger
from storyteller.project.models import ProjectContext
from storyteller.utils.chinese import count_chinese_chars
from storyteller.utils.markdown import parse_sections

log = get_logger("qa")

TARGET_MIN = 2000
TARGET_MAX = 3000


@dataclass
class QaResult:
    suggestions: str          # numbered list or "无需调整"
    needs_revision: bool      # False if LLM said no changes needed


async def qa_format_chapter(
    ctx: ProjectContext,
    settings: Settings,
    chapter_num: int,
    content: str,
) -> QaResult | None:
    """Check a chapter's length/format and return suggestions for writer to apply.

    Short-circuits when length is already in [TARGET_MIN, TARGET_MAX] to skip
    the LLM call. Caller owns chapter content loading.
    """
    if not content:
        log.warning("No content for chapter %d", chapter_num)
        return None

    char_count = count_chinese_chars(content)
    if TARGET_MIN <= char_count <= TARGET_MAX:
        log.info("Chapter %d already within target: %d chars", chapter_num, char_count)
        return QaResult(suggestions="无需调整", needs_revision=False)

    llm_config = settings.get_llm("qa")
    client = create_client_from_config(llm_config)

    response = client.call(
        system=qa_prompts.SYSTEM,
        user=qa_prompts.USER.format(
            chapter_num=chapter_num,
            chapter_content=content,
            current_chars=char_count,
        ),
    )

    sections = parse_sections(response)
    suggestions = sections.get("调整建议", "").strip()
    needs_revision = bool(suggestions) and "无需调整" not in suggestions

    log.info(
        "Chapter %d QA: chars=%d needs_revision=%s suggestions=%d chars",
        chapter_num, char_count, needs_revision, len(suggestions),
    )
    return QaResult(suggestions=suggestions, needs_revision=needs_revision)
