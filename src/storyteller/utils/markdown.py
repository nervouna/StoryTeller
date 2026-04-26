"""Markdown file I/O for chapters."""
from __future__ import annotations

from pathlib import Path


def chapter_path(project_dir: Path, chapter_num: int, title: str = "") -> Path:
    """Generate chapter file path.

    Format: 001_title.md or 001.md if no title.
    """
    prefix = f"{chapter_num:03d}"
    if title:
        safe_title = title.replace("/", "_").replace(" ", "_")[:30]
        return project_dir / "chapters" / f"{prefix}_{safe_title}.md"
    return project_dir / "chapters" / f"{prefix}.md"


def read_chapter(project_dir: Path, chapter_num: int) -> str | None:
    """Read a chapter file, searching by number prefix."""
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        return None
    for f in chapters_dir.glob(f"{chapter_num:03d}*.md"):
        return f.read_text(encoding="utf-8")
    return None


def write_chapter(project_dir: Path, chapter_num: int, title: str, content: str) -> Path:
    """Write a chapter file."""
    chapters_dir = project_dir / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)
    path = chapter_path(project_dir, chapter_num, title)
    path.write_text(content, encoding="utf-8")
    return path


def list_chapters(project_dir: Path) -> list[tuple[int, str]]:
    """List all chapters, returns [(chapter_num, filename), ...]."""
    chapters_dir = project_dir / "chapters"
    if not chapters_dir.exists():
        return []
    result = []
    for f in sorted(chapters_dir.glob("*.md")):
        num_str = f.stem.split("_")[0]
        try:
            num = int(num_str)
            result.append((num, f.name))
        except ValueError:
            continue
    return sorted(result)


def parse_sections(text: str) -> dict[str, str]:
    """Parse markdown ## headers into a dict of section_name -> content."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        if line.startswith("## "):
            if current_key:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_key:
        sections[current_key] = "\n".join(current_lines).strip()

    return sections


def read_outline(project_dir: Path) -> str:
    """Read outline.md."""
    outline_path = project_dir / "outline.md"
    if outline_path.exists():
        return outline_path.read_text(encoding="utf-8")
    return ""


def write_outline(project_dir: Path, content: str) -> Path:
    """Write outline.md."""
    path = project_dir / "outline.md"
    path.write_text(content, encoding="utf-8")
    return path
