# agent-teams — 一套团队，三个 CLI

> Tech Lead + 12 名专业 Agent，职责互不重叠，从**一份 YAML** 生成 **MiniMax Code（MCode）**、
> **Claude Code**、**Codex** 三个工具各自原生的配置。

[English](README.md) · MIT

```
$ mcode exec "你的角色是什么？"
我是 MCode，senior engineering team 的 Tech Lead，可委派 17 名 teammate。

$ claude --agent architect -p "state your role"
I'm the Architect — module boundaries, contracts, state machines, trade-offs.

$ codex exec "$(role architect)" "state your role"
ROLE=architect
```

## 为什么

三个 CLI 默认都是一个通用 agent。只要工作跨了专业——架构、接口契约、schema、安全、性能、测试策略——
就会塌缩进同一个角色、同一套直觉里，而且没有人负责「**不能做什么**」。

本仓库补齐这些专业分工，而且**按各工具原生的方式**落地：
MCode 用 Custom Agent、Claude Code 用 subagent、Codex 用角色指令——而不是硬套一种格式。

## 团队

| agent | 角色 | 负责 | 明确不做 |
|---|---|---|---|
| `architect` | Architect | 模块边界、契约、状态机、技术取舍 | 写生产代码 |
| `product-owner` | Product Owner | 用户故事、验收标准、范围、优先级 | 做设计或实现 |
| `ui-ux-designer` | UI/UX Designer | 流程、交互态、无障碍、文案 | 写前端代码 |
| `frontend-engineer` | Frontend Engineer | 视图、组件、状态、路由、样式 | 后端 / schema / 构建基建 |
| `backend-engineer` | Backend Engineer | 领域逻辑、API、持久化、事务 | 前端或运维 |
| `api-designer` | API Designer | 契约、版本兼容、错误模型 | 业务逻辑 |
| `data-engineer` | Data Engineer | schema、迁移、索引、回填 | API 面或应用代码 |
| `sre-engineer` | SRE Engineer | 构建、发布、CI、IaC、可观测性 | 产品功能 |
| `security-engineer` | Security Engineer | 威胁建模、authn/authz、密钥、依赖 | 功能实现 |
| `qa-engineer` | QA Engineer | 测试策略、套件、回归、缺陷复现 | 悄悄改产品代码 |
| `code-reviewer` | Code Reviewer | 正确性、约定、错误路径、可维护性 | 重写被审改动 |
| `performance-engineer` | Performance Engineer | profiling、预算、缓存、并发 | 大范围重构 |
| `tech-writer` | Tech Writer | README、API 文档、CHANGELOG、运维手册 | 记录未实现的行为 |

每个角色都带显式的 **Boundaries**。只有职责清单是会漂移的，边界才是真正让泳道互斥的东西。

## 目录结构

```
team.yaml            # 唯一事实来源：名单、职责、边界、交付物
capabilities.yaml    # 按 tier（read / write）到各工具的工具名映射
tools/generate.py    # 重新生成三套产物；--check 供 CI 使用
mcode/               # MiniMax Code：Custom Agent + .builtin 覆盖层 + 安装脚本
claude/              # Claude Code：subagent + 安装脚本 + 网关 settings
codex/               # Codex：角色 TOML + 名单索引 + 安装脚本
proxy/               # 单文件协议桥：Anthropic Messages + Responses → Chat Completions
```

| 工具 | 安装内容 | 原生机制 |
|---|---|---|
| MCode | `~/.minimax/agents/<name>/agent.md`（13 个 Custom Agent）+ `.builtin` 里的 Tech Lead 覆盖层 | Custom Agent 名单 + 内置覆盖 |
| Claude Code | `~/.claude/agents/<name>.md`（13 个 subagent） | `--agent` / Agent 工具的 `subagent_type` |
| Codex | `~/.codex/team/agents/<name>.toml` + `~/.codex/AGENTS.md` 名单块 | 多 Agent 工具 + 角色指令 |

## 安装

```bash
git clone https://github.com/hamr-hub/agent-teams.git
cd agent-teams

./mcode/install.sh      # MiniMax Code
./claude/install.sh     # Claude Code
./codex/install.sh      # Codex
```

三个安装脚本都是幂等、只增不删，覆盖前备份到 `<dir>/backup-team-agents-<时间戳>/`，均支持 `--dry-run`。

## 本地网关（无需厂商订阅）

如果模型在 OpenAI 兼容网关上，先起桥，再让 CLI 指过来：

```bash
UPSTREAM=http://localhost:7863 MODEL=cn:glm-5.3-flash \
UPSTREAM_API_KEY=<key> PORT=8787 python3 proxy/claude_gateway_proxy.py
```

Claude Code → `ANTHROPIC_BASE_URL=http://localhost:8787`；Codex → provider 设
`base_url="http://localhost:8787/v1"`、`wire_api="responses"`。细节见 [`proxy/README.md`](proxy/README.md)。

## 定制

改 `team.yaml`，然后：

```bash
python3 tools/generate.py           # 重新生成 mcode/ claude/ codex/
python3 tools/generate.py --check   # 产物漂移则失败（CI 用）
```

新增角色只需在 `team.yaml` 追加一个块，下次生成三端同时生效。

## 验证记录

| 检查 | 结果 |
|---|---|
| MCode — 名单可见 | 主 Agent 自述 Tech Lead，并列出全部可委派对象 |
| MCode — 自定义 Agent | `task agent_name='architect'` → `ROLE=architect`（此前是 `Unknown agent`） |
| MCode — 并行泳道 | `backend-engineer` → `api/spec.md`、`tech-writer` → `README.md`，互不交叉 |
| MCode — 两条 prompt 路径 | `--prompt-mode tui` 与 `coding` 均识别 Tech Lead 身份 |
| Claude Code — agent | `claude --agent architect -p ...` → `ROLE=architect` |
| Claude Code — 委派 | Agent 工具 `subagent_type: qa-engineer` 返回它自己的答案 |
| Codex — 角色指令 | `codex exec "<architect role>"` → `ROLE=architect` |
| Codex — 工具调用 | 通过 apply_patch 经桥成功创建 `hello.txt` |
| 协议桥 — 两种方言 | Messages 与 Responses 的流式/非流式均验证 |

## 已知限制

- **Codex 没有 Agent 注册表**。角色是 spawn 时传入的指令文本，靠指令 + sandbox 约束，而不是声明的工具白名单。
- **MCode 的 Custom Agent 禁止 `features:`**（该键只在内置镜像生效），生成器已省略。
- **升级会重置厂商文件**。`npm i -g @minimax-ai/code`、Claude Code 更新、Codex 更新后需重跑对应安装脚本。
- **Claude Code 的 settings 优先于 shell 环境变量**。`~/.claude/settings.json` 里的 `env` 会覆盖 export，
  网关配置请用 `--settings` 传入。
- 协议桥是兼容层，不是生产网关：没有鉴权、限流与重试。

## 许可

MIT —— 见 [LICENSE](LICENSE)。非官方社区定制。MiniMax Code、Claude Code、Codex 版权归各自厂商；
本仓库的 `proxy/` 与生成器为原创代码。
