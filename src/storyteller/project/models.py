"""Project context: shared state passed between pipeline modules."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field


class ChapterOutline(BaseModel):
    chapter_num: int
    title: str = ""
    summary: str = ""
    key_events: list[str] = Field(default_factory=list)
    characters_involved: list[str] = Field(default_factory=list)
    setting: str = ""
    word_count_target: int = 2500


class Outline(BaseModel):
    title: str = ""
    genre: str = ""
    logline: str = ""
    themes: list[str] = Field(default_factory=list)
    target_audience: str = ""
    chapters: list[ChapterOutline] = Field(default_factory=list)
    notes: str = ""


class ChapterDraft(BaseModel):
    chapter_num: int
    title: str = ""
    content: str = ""
    word_count: int = 0
    status: str = "draft"  # draft | reviewed | final
    critic_notes: str = ""


class TelescopeReport(BaseModel):
    trends: list[str] = Field(default_factory=list)
    popular_tropes: list[str] = Field(default_factory=list)
    popular_tags: list[str] = Field(default_factory=list)
    sample_summaries: list[str] = Field(default_factory=list)
    raw_data: str = ""


@dataclass
class ProjectContext:
    """Mutable state passed through the pipeline."""
    project_dir: Path
    db_path: Path
    outline: Outline | None = None
    chapters: list[ChapterDraft] = field(default_factory=list)
    telescope: TelescopeReport | None = None
    current_chapter: int = 0
    errors: list[str] = field(default_factory=list)
