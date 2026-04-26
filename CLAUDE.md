# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

StoryTeller is an AI novel writing pipeline. 6 modules chain together: Telescope (trends) → Idea King (outline) → Secretary (world DB) → Writer (draft) → Critic (polish) → QA (format). CLI entry point: `storyteller`.

## Architecture

- **src/storyteller/** — `src/` layout, installed as editable (`pip install -e .`)
- **modules/** — one file per pipeline stage, each exports an async function taking `(ProjectContext, Settings)`
- **llm/client.py** — `LLMClient` wrapping Anthropic SDK; `create_client_from_config(LLMConfig)` is the standard factory
- **llm/tools.py** — Anthropic tool-use definitions for DB queries (used by Writer/Critic)
- **llm/prompts/** — one `.py` per module's system/user prompts
- **db/** — SQLAlchemy 2.0 async + aiosqlite; `create_engine()` → `get_session_factory()` → session
- **project/models.py** — `ProjectContext` dataclass is the shared state passed through the pipeline
- **config.py** — Pydantic `Settings` loaded from `config.yaml`; `settings.get_llm(role)` for per-module LLM config

## Key Patterns

- LLM JSON extraction: `client.call_json(system, user)` — calls LLM then `_extract_json()` parses response (handles code blocks, finds `{...}` in text). DeepSeek does NOT support `output_config` with `json_schema`.
- DB sessions: use `session = factory()` + `try/finally: await session.close()` — the `async with factory() as session:` context manager auto-rollbacks on exit.
- Anthropic SDK pitfall: shell `ANTHROPIC_AUTH_TOKEN` overrides `api_key` param. `LLMClient.__init__` pops it before creating the client and restores after.

## Commands

```bash
# Setup
cp .env.example .env          # ST_API_KEY, ST_BASE_URL, ST_TAVILY_API_KEY
cp config.example.yaml config.yaml

# Run
storyteller new <name>         # Create project
storyteller run <name>         # Full pipeline (auto-skips completed steps)
storyteller outline <name>     # Interactive outline (or --auto)
storyteller settings <name>    # Sync world DB from outline
storyteller write <name> -c 1  # Write chapter 1
storyteller review <name> -c 1 # Review chapter 1
storyteller qa <name> -c 1     # Format chapter 1

# Test
.venv/bin/pytest tests/ -v          # 33 tests, uses pytest-asyncio for DB tests

# Lint
.venv/bin/ruff check src/           # Check
.venv/bin/ruff check src/ --fix     # Auto-fix
```

## Conventions

- Language: Python 3.11+, src/ layout, Click CLI, ruff linting (E/W/F/I/UP/B/SIM)
- Chinese: user-facing copy, prompts, chapter content. English: code symbols, variable names, comments.
- Config: `.env` for secrets (ST_* prefix), `config.yaml` for runtime settings, `config.example.yaml` checked in
- Projects stored in `projects/<name>/` (gitignored) — each has `world.db`, `outline.md`, `chapters/`
- LLM calls go through `LLMClient` — never instantiate `anthropic.Anthropic` directly
- Prompts live in `llm/prompts/` — one file per module, exported as `SYSTEM` and `USER` constants
- Tests use `pytest-asyncio` — async DB tests need `@pytest.mark.asyncio` decorator and `pytest_asyncio.fixture` for fixtures

## Gotchas

- `nest_asyncio.apply()` in cli.py — required because Writer/Critic tool handlers bridge sync/async via `run_until_complete`
- `_extract_json` in `llm/client.py` raises `ValueError` on failure; `modules/secretary.py` wraps it (catches ValueError, returns None)
- `parse_sections()` in `utils/markdown.py` is the shared `## header` parser — used by critic and qa modules
- Outline markdown format is coupled between `_outline_to_markdown()` and `load_outline_from_file()` in idea_king.py — changes to one must match the other
