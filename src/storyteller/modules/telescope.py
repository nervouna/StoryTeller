"""Telescope module (望远镜) — scan trending novel styles.

Data sources:
1. Book site scraping (起点/番茄/七猫/晋江)
2. Tavily web search
"""
from __future__ import annotations

from datetime import date

import httpx
from tavily import TavilyClient

from storyteller.config import Settings
from storyteller.llm.client import create_client_from_config
from storyteller.llm.prompts import telescope as telescope_prompts
from storyteller.log import get_logger
from storyteller.project.models import ProjectContext, TelescopeReport

log = get_logger("telescope")

# Book site search queries
_BOOK_SITE_QUERIES = [
    "起点中文网 热门小说 排行榜",
    "番茄小说 热门推荐",
    "七猫小说 排行榜",
    "晋江文学城 热门",
]

_GENERAL_QUERIES = [
    "网络小说 2026 流行趋势 热门题材",
    "网文 热门梗 热门设定",
    "网络小说 读者偏好 变化",
]


async def telescope_scan(ctx: ProjectContext, settings: Settings) -> ProjectContext:
    """Scan book sites + web for trending novel styles."""
    log.info("Starting telescope scan...")

    collected_data: list[str] = []

    # 1. Tavily search for book site trends
    tavily_key = settings.tavily.get("api_key") or ""
    if tavily_key:
        try:
            tavily = TavilyClient(api_key=tavily_key)
            for query in _BOOK_SITE_QUERIES + _GENERAL_QUERIES:
                try:
                    result = tavily.search(query, max_results=3, search_depth="basic")
                    snippets = [
                        f"### {r['title']}\n{r['content'][:300]}"
                        for r in result.get("results", [])
                    ]
                    if snippets:
                        collected_data.append(f"## 搜索: {query}\n" + "\n\n".join(snippets))
                except Exception as e:
                    log.warning("Tavily search failed for '%s': %s", query, e)
        except Exception as e:
            log.warning("Tavily client init failed: %s", e)
    else:
        log.warning("No Tavily API key configured, skipping web search")

    # 2. Direct HTTP scraping of book sites (basic approach)
    proxy = settings.proxy or None
    site_data = await _scrape_book_sites(proxy)
    collected_data.extend(site_data)

    if not collected_data:
        log.warning("No data collected, generating report from LLM knowledge only")
        collected_data.append("（无法获取实时数据，请基于你的知识分析当前网文市场趋势）")

    # 3. LLM analysis
    llm_config = settings.get_llm()
    client = create_client_from_config(llm_config)

    log.info("Analyzing trends with LLM...")
    raw = client.call(
        system=telescope_prompts.SYSTEM,
        user=telescope_prompts.USER.format(
            data="\n\n---\n\n".join(collected_data),
            date=date.today().isoformat(),
        ),
    )

    # 4. Parse report
    report = TelescopeReport(
        trends=_extract_list(raw, "流行趋势"),
        popular_tropes=_extract_list(raw, "热门题材"),
        popular_tags=_extract_list(raw, "值得关注的设定"),
        sample_summaries=_extract_list(raw, "创新建议"),
        raw_data=raw,
    )
    ctx.telescope = report

    # 5. Save to file
    telescope_path = ctx.project_dir / "telescope.md"
    telescope_path.write_text(raw, encoding="utf-8")
    log.info("Telescope report saved to %s", telescope_path)

    return ctx


async def _scrape_book_sites(proxy: str | None) -> list[str]:
    """Basic HTTP scraping of book site ranking pages."""
    data: list[str] = []
    transport = httpx.AsyncHTTPTransport(proxy=proxy) if proxy else None

    sites = [
        ("起点中文网", "https://www.qidian.com/rank/"),
        ("番茄小说", "https://fanqienovel.com/"),
    ]

    async with httpx.AsyncClient(transport=transport, follow_redirects=True, timeout=15) as client:
        for name, url in sites:
            try:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                })
                if resp.status_code == 200:
                    text = resp.text
                    # Extract basic info — full parsing would require beautifulsoup
                    # For MVP, just capture the raw page snippet
                    data.append(f"## {name} (HTTP {resp.status_code})\n页面长度: {len(text)} 字符")
                    log.info("Scraped %s: %d bytes", name, len(text))
                else:
                    log.warning("Scrape %s returned %d", name, resp.status_code)
            except Exception as e:
                log.warning("Failed to scrape %s: %s", name, e)

    return data


def _extract_list(text: str, section_name: str) -> list[str]:
    """Extract items from a ## section."""
    import re
    pattern = re.compile(rf"## {re.escape(section_name)}\s*\n(.*?)(?=\n## |\Z)", re.DOTALL)
    match = pattern.search(text)
    if not match:
        return []
    content = match.group(1).strip()
    items = []
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            items.append(line[2:].strip())
        elif line and not line.startswith("#"):
            items.append(line)
    return items
