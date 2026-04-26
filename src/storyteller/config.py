"""Configuration loader using Pydantic."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env from project root, override shell env so .env takes precedence
load_dotenv(override=True)


class LLMConfig(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 8192


class TelescopeConfig(BaseModel):
    book_sites: list[str] = Field(default_factory=lambda: ["qidian", "fanqie", "qimao", "jinjiang"])
    max_results_per_site: int = 10


class ProjectsConfig(BaseModel):
    root: str = "./projects"


class Settings(BaseModel):
    proxy: str = ""
    llm: dict[str, LLMConfig] = Field(default_factory=lambda: {"default": LLMConfig()})
    tavily: dict[str, str] = Field(default_factory=dict)
    projects: ProjectsConfig = Field(default_factory=ProjectsConfig)
    telescope: TelescopeConfig = Field(default_factory=TelescopeConfig)

    def get_llm(self, role: str = "default") -> LLMConfig:
        """Get LLM config by role, falling back to default."""
        if role in self.llm:
            return self.llm[role]
        return self.llm.get("default", LLMConfig())


def _clean_none(d: dict) -> dict:
    """Replace None values with empty dicts/lists to satisfy Pydantic defaults."""
    return {k: (v if v is not None else {}) for k, v in d.items()}


def _fill_env_defaults(raw: dict) -> dict:
    """Fill empty LLM/api fields from ST_* env vars."""
    llm = raw.get("llm") or {}
    for _role, cfg in llm.items():
        if not isinstance(cfg, dict):
            continue
        if not cfg.get("api_key"):
            cfg["api_key"] = os.environ.get("ST_API_KEY", "")
        if not cfg.get("base_url"):
            cfg["base_url"] = os.environ.get("ST_BASE_URL", "")
    tavily = raw.get("tavily") or {}
    if isinstance(tavily, dict) and not tavily.get("api_key"):
        tavily["api_key"] = os.environ.get("ST_TAVILY_API_KEY", "")
        raw["tavily"] = tavily
    return raw


def load_config(path: str | Path = "config.yaml") -> Settings:
    """Load settings from YAML config file."""
    config_path = Path(path)
    if config_path.exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        raw = _clean_none(raw)
        raw = _fill_env_defaults(raw)
        return Settings(**raw)
    return Settings()
