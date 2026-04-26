"""Create and load novel projects on disk."""
from __future__ import annotations

from pathlib import Path

from storyteller.config import Settings
from storyteller.project.models import ProjectContext


def get_projects_root(settings: Settings) -> Path:
    return Path(settings.projects.root)


def create_project(name: str, settings: Settings) -> ProjectContext:
    """Create a new novel project with directory structure."""
    root = get_projects_root(settings)
    project_dir = root / name
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "chapters").mkdir(exist_ok=True)

    outline_path = project_dir / "outline.md"
    if not outline_path.exists():
        outline_path.write_text(f"# {name}\n\n<!-- 大纲将在点子王讨论后生成 -->\n", encoding="utf-8")

    db_path = project_dir / "world.db"
    return ProjectContext(project_dir=project_dir, db_path=db_path)


def load_project(name: str, settings: Settings) -> ProjectContext:
    """Load an existing project."""
    root = get_projects_root(settings)
    project_dir = root / name
    if not project_dir.exists():
        raise FileNotFoundError(f"Project not found: {project_dir}")
    return ProjectContext(
        project_dir=project_dir,
        db_path=project_dir / "world.db",
    )


def list_projects(settings: Settings) -> list[str]:
    """List all project names."""
    root = get_projects_root(settings)
    if not root.exists():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and (d / "outline.md").exists()
    )
