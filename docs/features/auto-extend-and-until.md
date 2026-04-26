# PRD: Auto-Extend Outline & `--until N`

## Summary

当 Writer 写完大纲中的所有章节但未达到章数上限时，自动调用 Idea King 扩展大纲、Secretary 同步世界观，然后继续写作。通过 `run --until N` 控制最大写作章数。

## Problem

当前 `storyteller run` 的章节数完全由大纲决定。大纲有 20 章就写 20 章。对于长篇网文（100+ 章），用户需要：

1. 手动多次运行 `run`，每次手动扩展大纲
2. 每次扩展后手动同步世界观 DB
3. 手动判断从哪一章继续写

这三个手动步骤应自动化。

## User Story

作为一个网文作者，我想用 `storyteller run my-novel --until 100` 一键生成最多 100 章，系统自动在大纲耗尽时扩展大纲并继续写作，这样我不需要反复手动操作。

## Design

### 1. CLI 变更

```bash
# 新增 --until 选项
storyteller run my-novel --until 50

# 等价语义：写最多 50 章。如果大纲只有 20 章，写完后自动扩展。
# 如果不传 --until，行为与现在完全一致（写完大纲即停）。
```

`run` 命令签名变更：

```python
@click.option("--until", type=int, default=None,
              help="Maximum chapters to write. Auto-extends outline if needed.")
```

### 2. Pipeline 流程变更

当前流程（线性 6 步）：

```
Telescope → Idea King → Secretary → Writer/Critic/QA loop → done
```

新流程（加入扩展循环）：

```
Telescope → Idea King → Secretary → Write loop ─┐
                                    ↑             │
                              extend outline      │
                              re-sync secretary   │
                                    └─────────────┘
```

核心变更在 `cli.py` 的 `_full_pipeline()` 中，章数循环从 `for ch in chapters` 改为 `while` 循环：

```python
written = 0
max_extensions = 10          # 防止无限循环
extension_count = 0

while True:
    chapters_to_write = [ch.chapter_num for ch in project.outline.chapters]
    existing = {num for num, _ in list_chapters(project.project_dir)}

    for ch_num in chapters_to_write:
        if until and written >= until:
            break            # 达到章数上限

        # Writer（跳过已存在的）
        # Critic
        # QA
        written += 1

    # 判断是否需要扩展
    if until and written < until and extension_count < max_extensions:
        # 检查是否所有大纲章节都已写完
        all_written = all(
            ch.chapter_num in existing
            for ch in project.outline.chapters
        )
        if all_written:
            extension_count += 1
            console.print(f"\n💡 [bold]大纲已用尽，自动扩展 (第 {extension_count} 轮)...[/bold]")
            await idea_king_extend(project, settings)
            await secretary_sync(project, settings)
            continue               # 回到 while 顶部，用新大纲继续写
    break                          # 不需要扩展，退出
```

### 3. Idea King 扩展函数

新增 `idea_king_extend()` 到 `src/storyteller/modules/idea_king.py`。

**输入上下文：**

| 数据 | 来源 | 用途 |
|------|------|------|
| 现有大纲全文 | `outline.md` | 告诉 LLM 已有的故事结构 |
| 最后 2-3 章内容 | `chapters/*.md` | 保持剧情连续性 |
| 世界观摘要 | `secretary_dump()` | 新章节需要的世界观上下文 |
| 已写章节数 | `len(existing)` | 确定新章节的起始编号 |

**Prompt 设计：**

```python
EXTEND_SYSTEM = """你是小说策划师。作者正在写一部连载小说，当前大纲已写完，需要你扩展后续章节。

规则：
1. 延续现有故事线，不要重复已有内容
2. 新章节从第 {next_chapter} 章开始编号
3. 生成 {batch_size} 章大纲
4. 如果故事已自然完结，返回空的 chapters 数组
5. 保持世界观一致性

以 JSON 格式输出，格式与初始大纲相同。"""
```

**关键行为：**

- `next_chapter` = 现有大纲最后一章的 `chapter_num + 1`
- `batch_size` = `min(10, until - written)`，即不超过剩余需要的章数
- LLM 返回空 `chapters` 数组 → 故事自然完结，停止扩展
- 新章节追加到 `project.outline.chapters`（不替换）
- 追加写入 `outline.md`（不覆盖）

**函数签名：**

```python
async def idea_king_extend(
    ctx: ProjectContext,
    settings: Settings,
) -> ProjectContext:
    """Extend existing outline with more chapters.

    Reads the current outline + last few chapters for context,
    asks LLM to generate the next batch of chapter outlines.
    Appends to ctx.outline and outline.md.
    """
```

### 4. Secretary 同步策略

扩展后需要重新同步世界观。当前 `secretary_sync()` 执行全量 DELETE + INSERT。

**方案：保持全量同步。**

原因：
- `secretary_sync()` 的输入是完整大纲（包括旧章节 + 新章节）
- LLM 会从完整大纲中提取所有角色/势力/道具
- 全量同步保证一致性，不会出现增量遗漏
- 实现简单，不需要改 Secretary 模块

唯一变更：`_outline_to_text()` 已经遍历 `outline.chapters`，扩展后自然包含新章节。

### 5. 边界情况处理

| 场景 | 行为 |
|------|------|
| `--until` 未传 | 行为不变，写完大纲即停 |
| `--until` < 大纲章数 | 只写前 N 章，不扩展 |
| `--until` = 大纲章数 | 写完即停，不扩展 |
| LLM 返回空 chapters | 故事完结，停止扩展，打印提示 |
| 扩展 10 轮仍未到 N | 停止，打印警告 |
| 大纲中已有部分章节已写 | 跳过已写章节，正常继续 |
| `--chapter` 与 `--until` 同时使用 | `--chapter` 写单章，`--until` 忽略（互斥） |

### 6. Outline.md 追加格式

扩展后的 `outline.md` 在 `## 章节大纲` 部分追加新章节，格式与现有完全一致：

```markdown
## 章节大纲

### 第1章 - 原有章节
...

### 第20章 - 原有最后一章
...

### 第21章 - 扩展章节（自动追加）
**摘要**: ...
**关键事件**: ...
**出场人物**: ...
**地点**: ...
```

`load_outline_from_file()` 的正则 `### 第(\d+)章 - (.+)` 自然匹配新章节，无需修改解析逻辑。

### 7. 新增 Prompt 文件

`src/storyteller/llm/prompts/idea_king.py` 新增：

```python
EXTEND_SYSTEM = """你是小说策划师。作者正在写一部连载小说，当前大纲的所有章节已写完，需要你规划后续剧情。

规则：
1. 仔细阅读现有大纲和最近几章的内容，延续故事线
2. 不要重复已有情节，不要推翻已建立的设定
3. 新章节从第 {next_chapter} 章开始编号
4. 生成 {batch_size} 章的详细大纲
5. 如果故事在此处已自然完结（主线冲突已解决），返回空的 chapters 数组
6. 注意节奏：不要在一个批次内推进过快

以 JSON 格式输出，格式与初始大纲相同。"""

EXTEND_USER = """现有大纲：
{outline_text}

最近几章内容：
{recent_chapters}

世界观摘要：
{world_summary}

请基于以上信息，生成接下来 {batch_size} 章的大纲。"""
```

## File Changes

| File | Change |
|------|--------|
| `src/storyteller/cli.py` | `run` 命令新增 `--until` 选项；章数循环从 `for` 改为 `while` + 扩展逻辑 |
| `src/storyteller/modules/idea_king.py` | 新增 `idea_king_extend()` 函数 |
| `src/storyteller/llm/prompts/idea_king.py` | 新增 `EXTEND_SYSTEM` 和 `EXTEND_USER` prompt |
| `tests/test_idea_king.py` | 新增 `idea_king_extend` 单元测试 |
| `tests/test_cli.py` | 新增 `--until` 相关测试 |

## Non-Goals

- 不改 Secretary 模块（保持全量同步）
- 不改 Writer/Critic/QA 模块（它们只关心单个 chapter_num）
- 不引入章节队列/任务系统（保持简单 while 循环）
- 不支持"每写 N 章扩展一次"（只在大纲耗尽时扩展）
- 不支持用户交互式确认扩展内容（自动模式）

## Verification

```bash
# 1. 不传 --until，行为不变
storyteller run test-novel
# → 写完大纲章节数即停

# 2. --until 大于大纲章数，触发扩展
storyteller run test-novel --until 15
# → 写完大纲 10 章后，自动扩展 5 章

# 3. --until 小于大纲章数，不扩展
storyteller run test-novel --until 5
# → 只写前 5 章

# 4. 单元测试
.venv/bin/pytest tests/ -v
.venv/bin/ruff check src/
```
