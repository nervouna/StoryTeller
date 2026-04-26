"""CLI entry point for StoryTeller."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click
import nest_asyncio
from rich.console import Console
from rich.table import Table

from storyteller.config import load_config
from storyteller.log import setup_logging

nest_asyncio.apply()

console = Console()


def _run(coro):
    """Run an async function from sync click context."""
    return asyncio.run(coro)


@click.group()
@click.option("--config", "config_path", default="config.yaml", help="Config file path")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx, config_path, verbose):
    """StoryTeller — AI-powered novel writing pipeline."""
    setup_logging("DEBUG" if verbose else "INFO")
    ctx.ensure_object(dict)
    ctx.obj["settings"] = load_config(config_path)


# ---------- Project Management ----------


@cli.command()
@click.argument("name")
@click.pass_context
def new(ctx, name):
    """Create a new novel project."""
    from storyteller.project.manager import create_project

    settings = ctx.obj["settings"]
    project = create_project(name, settings)
    console.print(f"[green]✅ Created project:[/green] {project.project_dir}")
    console.print(f"   DB: {project.db_path}")
    console.print(f"   Run [bold]storyteller outline {name}[/bold] to start discussing the outline")


@cli.command()
@click.pass_context
def list(ctx):
    """List all novel projects."""
    from storyteller.project.manager import list_projects

    settings = ctx.obj["settings"]
    projects = list_projects(settings)
    if not projects:
        console.print("[yellow]No projects found.[/yellow] Create one with: storyteller new <name>")
        return
    table = Table(title="Novel Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Path")
    for name in projects:
        root = Path(settings.projects.root)
        table.add_row(name, str(root / name))
    console.print(table)


# ---------- Pipeline Steps ----------


@cli.command()
@click.argument("name")
@click.option("--auto", is_flag=True, help="Generate outline without human interaction")
@click.option("--genre", default="", help="Novel genre (for auto mode)")
@click.option("--premise", default="", help="Story premise (for auto mode)")
@click.pass_context
def outline(ctx, name, auto, genre, premise):
    """Discuss and create novel outline (点子王)."""
    from storyteller.modules.idea_king import idea_king_auto, idea_king_interactive
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    if auto:
        _run(idea_king_auto(project, settings, genre=genre, premise=premise))
    else:
        _run(idea_king_interactive(project, settings))


@cli.command()
@click.argument("name")
@click.pass_context
def telescope(ctx, name):
    """Scan trending novel styles (望远镜)."""
    from storyteller.modules.telescope import telescope_scan
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    _run(telescope_scan(project, settings))
    console.print(f"[green]✅ Telescope report saved to[/green] {project.project_dir / 'telescope.md'}")


@cli.command()
@click.argument("name")
@click.option("--query", "-q", default="", help="Natural language query")
@click.option("--dump", is_flag=True, help="Dump all settings")
@click.pass_context
def settings(ctx, name, query, dump):
    """Manage world-building settings (秘书长)."""
    from storyteller.db.engine import create_engine, get_session_factory
    from storyteller.modules.idea_king import load_outline_from_file
    from storyteller.modules.secretary import secretary_dump, secretary_query, secretary_sync
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)

    async def _run_settings():
        engine = await create_engine(project.db_path)
        factory = get_session_factory(engine)
        session = factory()
        try:
            if query:
                result = await secretary_query(session, query)
                console.print(result)
            elif dump:
                result = await secretary_dump(session)
                console.print(result)
            else:
                # Load outline from disk if not in memory
                if not project.outline:
                    project.outline = load_outline_from_file(project.project_dir)
                if not project.outline:
                    console.print("[yellow]⚠️  No outline found. Run 'storyteller outline' first.[/yellow]")
                    return
                await secretary_sync(project, settings)
                console.print("[green]✅ Settings synced from outline[/green]")
        finally:
            await session.close()
            await engine.dispose()

    _run(_run_settings())


@cli.command()
@click.argument("name")
@click.option("--chapter", "-c", type=int, help="Chapter number to write")
@click.pass_context
def write(ctx, name, chapter):
    """Write chapter(s) (没头脑)."""
    from storyteller.modules.writer import writer_draft_chapter
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    _run(writer_draft_chapter(project, settings, chapter_num=chapter))
    console.print("[green]✅ Chapter(s) written[/green]")


@cli.command()
@click.argument("name")
@click.option("--chapter", "-c", type=int, help="Chapter number to review")
@click.pass_context
def review(ctx, name, chapter):
    """Review and polish chapter(s) (不高兴)."""
    from storyteller.modules.critic import critic_review_chapter
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    _run(critic_review_chapter(project, settings, chapter_num=chapter))
    console.print("[green]✅ Chapter(s) reviewed[/green]")


@cli.command()
@click.argument("name")
@click.option("--chapter", "-c", type=int, help="Chapter number to format")
@click.pass_context
def qa(ctx, name, chapter):
    """Format chapter(s) to web novel standard (质检员)."""
    from storyteller.modules.qa import qa_format_chapter
    from storyteller.project.manager import load_project

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    _run(qa_format_chapter(project, settings, chapter_num=chapter))
    console.print("[green]✅ Chapter(s) formatted[/green]")


# ---------- Full Pipeline ----------


@cli.command()
@click.argument("name")
@click.option("--chapter", "-c", type=int, help="Write only this chapter")
@click.option("--until", "-u", type=int, default=0,
              help="Maximum chapters to write; auto-extends outline if needed.")
@click.option("--auto-outline", is_flag=True, help="Auto-generate outline without human interaction")
@click.option("--genre", default="", help="Novel genre (for --auto-outline)")
@click.option("--premise", default="", help="Story premise (for --auto-outline)")
@click.option("--auto-accept", is_flag=True, help="Auto-accept critic review without prompt")
@click.option("--skip-telescope", is_flag=True, help="Skip telescope scan")
@click.option("--skip-outline", is_flag=True, help="Skip outline discussion")
@click.pass_context
def run(ctx, name, chapter, until, auto_outline, genre, premise, auto_accept, skip_telescope, skip_outline):
    """Run the full writing pipeline."""
    import sqlite3

    from storyteller.modules.critic import critic_review_chapter
    from storyteller.modules.idea_king import (
        idea_king_auto,
        idea_king_extend,
        idea_king_interactive,
        load_outline_from_file,
    )
    from storyteller.modules.qa import qa_format_chapter
    from storyteller.modules.secretary import secretary_sync
    from storyteller.modules.telescope import telescope_scan
    from storyteller.modules.writer import writer_draft_chapter
    from storyteller.project.manager import load_project
    from storyteller.utils.markdown import list_chapters

    settings = ctx.obj["settings"]
    project = load_project(name, settings)

    async def _full_pipeline():
        # Step 1: Telescope
        telescope_path = project.project_dir / "telescope.md"
        if skip_telescope:
            console.print("\n🔭 [dim]Step 1: Telescope — skipped (flag)[/dim]")
        elif telescope_path.exists():
            console.print("\n🔭 [dim]Step 1: Telescope — already done[/dim]")
        else:
            console.print("\n🔭 [bold]Step 1: Telescope[/bold] — scanning trends...")
            await telescope_scan(project, settings)

        # Step 2: Idea King
        outline_path = project.project_dir / "outline.md"
        has_outline = outline_path.exists() and outline_path.read_text(encoding="utf-8").strip()
        if skip_outline:
            console.print("\n💡 [dim]Step 2: Idea King — skipped (flag)[/dim]")
        elif has_outline and not chapter:
            console.print("\n💡 [dim]Step 2: Idea King — already done[/dim]")
        elif auto_outline:
            console.print("\n💡 [bold]Step 2: Idea King[/bold] — auto-generating outline...")
            await idea_king_auto(project, settings, genre=genre, premise=premise)
        else:
            console.print("\n💡 [bold]Step 2: Idea King[/bold] — outline discussion...")
            await idea_king_interactive(project, settings)

        # Load outline for later steps
        if not project.outline:
            project.outline = load_outline_from_file(project.project_dir)

        # Step 3: Secretary
        db_has_data = False
        if project.db_path.exists():
            conn = sqlite3.connect(str(project.db_path))
            count = conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0]
            conn.close()
            db_has_data = count > 0

        if db_has_data:
            console.print("\n📋 [dim]Step 3: Secretary — already synced[/dim]")
        else:
            if not project.outline:
                console.print("\n📋 [yellow]Step 3: Secretary — no outline, skipping[/yellow]")
            else:
                console.print("\n📋 [bold]Step 3: Secretary[/bold] — syncing world settings...")
                await secretary_sync(project, settings)

        # Step 4-6: Per-chapter loop with auto-extend
        extension_count = 0
        max_extensions = 10

        while True:
            if not project.outline:
                break

            chapters_to_write = [chapter] if chapter else [
                ch.chapter_num for ch in project.outline.chapters
            ]
            existing_chapters = {num for num, _ in list_chapters(project.project_dir)}
            unwritten = [ch for ch in chapters_to_write if ch not in existing_chapters]

            if not unwritten:
                # All current outline chapters written — try extending
                if until > 0 and project.outline.chapters and extension_count < max_extensions:
                    max_ch = max(ch.chapter_num for ch in project.outline.chapters)
                    if max_ch < until:
                        extension_count += 1
                        console.print(
                            f"\n🔄 [bold]大纲已用尽，自动扩展 (第 {extension_count}/{max_extensions} 轮)...[/bold]"
                        )
                        await idea_king_extend(project, settings, target_chapter=until)
                        console.print("📋 [bold]重新同步世界观...[/bold]")
                        await secretary_sync(project, settings)
                        continue
                break

            for ch_num in unwritten:
                # Writer
                console.print(f"\n✍️  [bold]Writing chapter {ch_num}...[/bold]")
                await writer_draft_chapter(project, settings, chapter_num=ch_num)

                # Critic — always review (user might want fresh review)
                console.print(f"\n😤 [bold]Reviewing chapter {ch_num}...[/bold]")
                await critic_review_chapter(project, settings, chapter_num=ch_num, auto_accept=auto_accept)

                # QA
                console.print(f"\n✅ [bold]QA formatting chapter {ch_num}...[/bold]")
                await qa_format_chapter(project, settings, chapter_num=ch_num)

            if chapter:
                break  # single-chapter mode, don't loop

        console.print("\n[green bold]🎉 Pipeline complete![/green bold]")

    _run(_full_pipeline())


# ---------- Inspection ----------


@cli.command()
@click.argument("name")
@click.pass_context
def show(ctx, name):
    """Show project overview and progress."""
    from storyteller.project.manager import load_project
    from storyteller.utils.markdown import list_chapters, read_outline

    settings = ctx.obj["settings"]
    project = load_project(name, settings)

    console.print(f"\n📖 [bold cyan]{name}[/bold cyan]")
    console.print(f"   Path: {project.project_dir}")

    # Outline
    outline_text = read_outline(project.project_dir)
    if outline_text and not outline_text.startswith("# " + name):
        console.print(f"\n📝 Outline: {len(outline_text)} chars")
        # Show first few lines
        lines = outline_text.split("\n")[:5]
        for line in lines:
            console.print(f"   {line}")
    else:
        console.print("\n📝 [yellow]No outline yet[/yellow]")

    # Chapters
    chapters = list_chapters(project.project_dir)
    if chapters:
        console.print(f"\n📚 Chapters ({len(chapters)}):")
        for _num, filename in chapters:
            path = project.project_dir / "chapters" / filename
            content = path.read_text(encoding="utf-8")
            from storyteller.utils.chinese import count_chinese_chars

            chars = count_chinese_chars(content)
            console.print(f"   {filename} — {chars} chars")
    else:
        console.print("\n📚 [yellow]No chapters yet[/yellow]")

    # Telescope
    telescope_path = project.project_dir / "telescope.md"
    if telescope_path.exists():
        console.print("\n🔭 Telescope report: available")
    else:
        console.print("\n🔭 [yellow]No telescope report[/yellow]")


@cli.command()
@click.argument("name")
@click.pass_context
def export(ctx, name):
    """Export all chapters as a single file."""
    from storyteller.project.manager import load_project
    from storyteller.utils.markdown import list_chapters

    settings = ctx.obj["settings"]
    project = load_project(name, settings)
    chapters = list_chapters(project.project_dir)

    if not chapters:
        console.print("[yellow]No chapters to export[/yellow]")
        return

    parts = [f"# {name}\n"]
    for _num, filename in chapters:
        path = project.project_dir / "chapters" / filename
        content = path.read_text(encoding="utf-8")
        parts.append(content)

    output = "\n\n---\n\n".join(parts)
    export_path = project.parent / f"{name}_export.md"
    export_path.write_text(output, encoding="utf-8")
    console.print(f"[green]✅ Exported to[/green] {export_path}")


if __name__ == "__main__":
    cli()
