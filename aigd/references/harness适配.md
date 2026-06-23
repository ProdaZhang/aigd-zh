# 跨 harness 适配（Claude Code / Codex / Gemini CLI / Copilot CLI）

> AIGD 的**包结构本身是跨 harness 通用的**:四家都用"一个子目录 + `SKILL.md`(`name`/`description` frontmatter)"这套 skill 格式,子 skill 用 `../aigd/references/` 取方法论的相对路径在哪家都成立(只要 7 个文件夹平级)。
> 不同的只有三件:**装哪个目录、怎么唤起、读写/跑命令用哪个工具名**。本页一次说清。方法论正文一律"说动作"(读/写/跑/搜),工具名按本表对应到你的 harness。

---

## 1. 装哪 + 怎么唤起

| harness | skills 目录 | 唤起方式 | 指令文件(本包不依赖) |
|---------|------------|----------|----------------------|
| **Claude Code** | `.claude/skills/`(项目) 或 `~/.claude/skills/`(用户) | `Skill` 工具 | `CLAUDE.md` |
| **Codex** | `~/.codex/skills/` **或** `~/.agents/skills/` | 原生加载,直接照 SKILL.md 走(无显式唤起工具) | `AGENTS.md` |
| **Gemini CLI** | `~/.gemini/skills/` **或** `~/.agents/skills/` | `activate_skill` 工具 | `GEMINI.md` |
| **Copilot CLI** | `~/.agents/skills/` | `skill` 工具 | — |

> **一次装、三家通用**:`~/.agents/skills/` 是 **Codex / Gemini / Copilot 共享的跨运行时路径**。把 7 个文件夹放这一处,这三家都能发现(Gemini 里 `~/.agents/skills/` 优先于 `~/.gemini/skills/`)。Claude Code 单独用 `.claude/skills/`。
> 无论装哪,**7 个文件夹(`aigd` + 6 个 `aigd-*`)必须平级**——子 skill 靠同级 `aigd/` 取 references,缺了或层级错就断链。

---

## 2. 工具名对应（方法论"说动作" → 各 harness 工具）

| 动作 | Claude Code | Codex | Gemini CLI |
|------|-------------|-------|-----------|
| 读文件 | `Read` | `shell`(`cat`/`head`) | `read_file` / `read_many_files` |
| 写新文件 | `Write` | `apply_patch` | `write_file` |
| 改文件 | `Edit` | `apply_patch` | `replace` |
| 跑命令 | `Bash` | `shell` | `run_shell_command` |
| 搜内容 | `Grep` | `shell`(`grep`/`rg`) | `grep_search` |
| 找文件 | `Glob` | `shell`(`find`/`ls`) | `glob` / `list_directory` |
| 派子 agent | `Agent` | `spawn_agent`(需 `multi_agent=true`) | `invoke_agent`(`@generalist`) |
| 任务跟踪 | `TodoWrite` | `update_plan` | `write_todos` |

校验器脚本是 `argv` 驱动的纯命令行(`python …/config_check.py …`),**跟 harness 无关**——任何能跑 shell 的环境都一样用,只要有 Python。

---

## 3. 两个 harness 相关的坑（方法论/速查里已泛化,这里给具体写法）

### 工具调用格式
不同 harness 的 function-call 块语法不同,**用错会静默不执行**(文件没写、命令没跑,却以为做了)。发前核一遍你 harness 要求的格式:
- **Claude Code**:必须带 `antml:` 命名空间前缀(写成裸 `invoke`/`parameter` → "tool call was malformed" 静默丢弃)。
- **Codex / Gemini**:按各自的工具调用协议;调用后确认产物真落盘(`shell ls` / `read_file` 复核),别假设已生效。

### 写文件用 UTF-8 无 BOM
中文文件被加 BOM / 变 UTF-16 会让下游读出乱码。各环境写法:
- **Claude Code**:`Write`/`Edit` 默认无 BOM,直接用;**别**用裸 PowerShell `Out-File`/`Set-Content`(会加 BOM)。Windows 下非要用 PowerShell 写中文 → `New-Object System.Text.UTF8Encoding $false`。
- **Codex(apply_patch)/ Gemini(write_file)**:默认 UTF-8 无 BOM,直接用。
- 通用底线:**落盘前确认是 UTF-8 无 BOM**,跨平台用 `/` 路径。

---

## 4. 指令文件(CLAUDE.md / AGENTS.md / GEMINI.md)

**AIGD 不建也不依赖任何 harness 的指令文件**——把"建 CLAUDE.md/AGENTS.md"塞进方法论会把它绑死在某 harness。本包只要求一个**改动账本**(默认项目根 `CHANGELOG.md`,见方法论「项目环境前置」),与指令文件无关。所以换 harness 时**指令文件那一栏可以无视**,装好 7 个文件夹 + 有 Python 即可。
