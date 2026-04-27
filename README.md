# StoryTeller

AI 小说写作流水线。6 个模块协作，从市场调研到成稿一条龙。

## 模块

| 模块 | CLI 命令 | 职责 |
|------|----------|------|
| 🔭 望远镜 | `storyteller telescope` | 扫描热门小说风格、梗、趋势 |
| 💡 点子王 | `storyteller outline` | 讨论并生成大纲（可 `--auto` 无人值守） |
| 📋 秘书长 | `storyteller settings` | 从大纲提取世界观设定入 SQL |
| ✍️ 没头脑 | `storyteller write` | 写章节草稿 / 按审稿意见改写 |
| 😤 不高兴 | `storyteller review` | 审稿，给出分级修改建议（🔴严重 / 🟡中等 / 🟢轻微） |
| ✅ 质检员 | `storyteller qa` | 检查篇幅和格式，给出调整建议 |

**写审分离**：没头脑是唯一生成正文的角色，不高兴和质检员只产出建议清单，由没头脑在流水线中应用。

```
没头脑(初稿)
  → 不高兴审 × 最多 3 轮（没 🔴 严重问题即通过，每轮之间由没头脑按建议改写）
  → 质检员查篇幅（可选一次改写）
  → 最终落盘
```

独立命令 `storyteller review / qa` 只打印建议供人类参考，**不会修改章节文件**。

## 快速开始

```bash
# 1. 安装依赖
python3 -m venv .venv
.venv/bin/pip install -e .

# 2. 配置 API
cp .env.example .env
cp config.example.yaml config.yaml
# 编辑 .env 填入你的 API Key 和 Provider URL

# 3. 创建项目
.venv/bin/storyteller new 我的仙侠

# 4. 运行完整流水线
.venv/bin/storyteller run 我的仙侠
```

## CLI 命令

```bash
# 项目管理
storyteller new <name>              # 创建项目
storyteller list                    # 列出项目
storyteller show <name>             # 查看项目进度

# 流水线（完整）
storyteller run <name>              # 望远镜 → 点子王 → 秘书长 → 写作循环
storyteller run <name> --chapter 3  # 只写第 3 章
storyteller run <name> --skip-telescope  # 跳过趋势扫描

# 单步执行
storyteller telescope <name>        # 扫描趋势
storyteller outline <name>          # 讨论大纲（交互式）
storyteller outline <name> --auto --genre 仙侠 --premise "废柴逆袭"  # 自动生成
storyteller settings <name>         # 用 LLM 从大纲提取世界观设定，写入 DB
storyteller settings <name> --dump  # 查看所有设定
storyteller settings <name> -q "金丹期以上的角色"  # 自然语言查询
storyteller write <name> -c 1       # 写第 1 章草稿
storyteller review <name> -c 1      # 打印第 1 章的审核建议（不改文件）
storyteller qa <name> -c 1          # 打印第 1 章的篇幅/格式建议（不改文件）

# 导出
storyteller export <name>           # 合并所有章节为单文件
```

## 项目结构

```
projects/我的仙侠/
├── world.db          # SQLite — 角色、势力、道具、规则等
├── outline.md        # 大纲
├── telescope.md      # 趋势报告
└── chapters/
    ├── 001_初入仙门.md
    └── 002_奇遇.md
```

## 配置

`.env` — API 密钥（使用 `ST_` 前缀避免与 shell 环境变量冲突）：

```env
ST_API_KEY=sk-xxx
ST_BASE_URL=https://your-provider.com   # 留空用官方 API
ST_TAVILY_API_KEY=tvly-xxx              # 可选，望远镜搜索用
```

`config.yaml` — 运行配置：

```yaml
proxy: "socks5://127.0.0.1:7890"    # 代理

llm:
  default:
    api_key: ""                       # 留空，自动读 ST_API_KEY
    base_url: ""                      # 留空，自动读 ST_BASE_URL
    model: "deepseek-v4-pro"          # 或其他模型
    max_tokens: 8192
  # 可按角色覆盖：writer / critic 单独配模型
  # writer:
  #   model: "deepseek-v4-pro"

projects:
  root: "./projects"
```

## 世界观 DB

Secretary 自动从大纲提取并写入 SQLite，包含：

- **Character** — 角色（境界、性格、外貌、目标）
- **Faction** — 势力（领袖、成员、领地）
- **Item** — 道具（法宝、丹药、功法）
- **WorldRule** — 世界规则（用于 Consistency Check）
- **PowerSystem** — 修炼等级体系
- **WorldRegion** — 世界区域
- **Economy** — 货币体系
- **CharacterRelationship** — 角色关系

Writer 写作时通过 tool-use 实时查询 DB，确保设定不矛盾。

## 开发

```bash
.venv/bin/pip install -e ".[dev]"   # 安装开发依赖
.venv/bin/pytest tests/ -v          # 运行测试
.venv/bin/ruff check src/           # Lint
.venv/bin/ruff check src/ --fix     # 自动修复
```

非小型改动（流水线模块、DB schema、LLM client、tool handler）完成后，跑完整验证：

```bash
.venv/bin/pytest tests/ -v && .venv/bin/ruff check src/
```

涉及 Writer/Critic tool-use 路径的变更，还需对实际项目做 smoke-test：

```bash
storyteller write <name> -c 1
```
