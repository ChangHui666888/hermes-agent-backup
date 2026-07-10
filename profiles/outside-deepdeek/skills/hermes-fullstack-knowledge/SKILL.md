---
name: hermes-fullstack-knowledge
description: Hermes Agent 满配架构知识库 — 12层架构、输入系统、Memory/Skill/MCP/Cron 等核心机制的系统化理解
version: 1.0.0
---

# Hermes Agent 满配知识体系

基于知乎《Hermes Agent 保姆级教程》7万字教程的核心精华整理。

---

## 核心哲学

**满配不是"装满"，而是"组合成可长期维护的个人Agent系统"**

> 围绕真实工作模式，把输入、记忆、技能、工具、自动化、可视化、Token成本和多Agent协同组合成一个可持续进化的系统。

---

## 一、12层架构（L1-L12）

| 层级 | 模块 | 解决问题 | 必备度 |
|------|------|----------|--------|
| L1 | 安装与模型Provider | 稳定运行 | **必配** |
| L2 | 输入系统 (SOUL/AGENTS/MEMORY) | Agent理解你和项目 | **必配** |
| L3 | Memory长期记忆 | 跨会话记住偏好 | **必配** |
| L4 | Skills技能系统 | 沉淀可复用流程 | **必配** |
| L5 | Tools/Toolsets | 控制本地能力 | **必配** |
| L6 | MCP外部工具 | 接GitHub/搜索/数据库 | 进阶 |
| L7 | Gateway消息入口 | 飞书/Telegram | 按需 |
| L8 | Cron自动化 | 定时日报/巡检 | **强烈推荐** |
| L9 | Profiles多实例 | 不同场景独立Agent | **强烈推荐** |
| L10 | 可视化与可观测 | 看见做了什么/哪里失败 | 进阶 |
| L11 | Token精简与上下文 | 降成本提速度 | 进阶 |
| L12 | 多Agent/24h团队 | 多角色长期协作 | 高阶 |

**建议顺序：先跑通 → 再记住你 → 再沉淀技能 → 再接工具 → 再定时运行 → 再多入口 → 最后多Agent协同**

---

## 二、输入系统：分层协议栈

### 5层模型

```
SOUL.md    → 工作协议（立场、职责、边界、风格）
USER.md    → 用户画像（你是谁、偏好什么）
MEMORY.md  → 工作笔记（项目、环境、踩坑经验）
AGENTS.md  → 目录规则（当前项目的规范）
SKILL.md   → 可复用任务流程（怎么做事的模板）
```

### SOUL.md 关键设计

解决 Agent **何时主动、何时刹车、何时反对你** 的实际问题：

- **立场**：直接、务实、有判断力、高主动性
- **职责**：主动推动事情，不等待完美指令
- **边界**：明确哪些事可直接做，哪些必须确认
- **反对机制**：可反对你，但需数据/例子/替代方案
- **沟通风格**：简单时简短，复杂时结构化，有风险写权衡

### USER.md vs MEMORY.md

| 文件 | 容量 | 适合写什么 |
|------|------|-----------|
| USER.md | ~1375字符 | 身份、技术背景、沟通/输出偏好、协作风格 |
| MEMORY.md | ~2200字符 | 项目进展、环境事实、踩坑经验、决策原则 |

**核心区别：USER.md写"你是谁"，MEMORY.md写"你在做什么"**

---

## 三、Memory / Skill / MCP 概念区分

| 概念 | 解决问题 | 举例 |
|------|---------|------|
| **Memory** | 记住"你是谁"和"你在做什么" | 偏好、项目背景 |
| **Skill** | 记住"你怎么做事" | 分析工具的固定流程 |
| **MCP Tool** | 连接"你能用什么外部工具" | GitHub搜索 |
| **Prompt** | 这次对话的临时指令 | "帮我看看这个链接" |

> **Memory是你的知识，Skill是你的方法论，MCP Tool是你的工具箱**

---

## 四、Skills 最佳实践

### 安装前5问
1. 是否服务长期目标？
2. 是否减少重复劳动？
3. 是否和已有Skill重复？
4. 是否需要危险权限？
5. 适合常驻还是临时启用？

**常驻Skill不超过5个。超过说明在用数量代替质量。**

### SKILL.md 结构
```yaml
---
name: skill-name
description: 简短描述
version: 1.0.0
---
# Skill Title

## 什么时候使用
触发条件

## 步骤
1. ...
2. ...

## 陷阱
- 常见错误1
- 常见错误2

## 验证
怎样算完成
```

---

## 五、安全审批四级

| 等级 | 典型工具 | 审批方式 |
|------|---------|----------|
| 安全 | read_file, web_search | 无需审批 |
| 低风险 | write_file, edit_file | 首次审批可记住 |
| 中风险 | execute_python, delegate_task | 每次审批 |
| 高风险 | execute_shell, kill_process | 强制审批 |

---

## 六、Profiles 隔离体系

```bash
hermes profile list          # 列出所有
hermes profile create NAME   # 创建（--clone-all）
hermes profile use NAME      # 设默认
hermes profile delete NAME   # 删除
hermes profile show NAME     # 查看详情
```

每个 Profile 独享：config.yaml / .env / sessions / skills / memory / cron / plugins

**日常使用原则**: 工作一个Profile，个人一个Profile，实验一个Profile。

---

## 七、Cron 定时任务

```bash
hermes cron create "30m"     # 每30分钟
hermes cron create "every 2h" # 每2小时
hermes cron create "0 9 * * *" # 每天9点
hermes cron list
hermes cron run <id>
```

**适合场景**: 日报生成 / 巡检 / 知识库更新 / 定时发布

---

## 八、Gateway 消息入口

支持平台：Telegram / Discord / Slack / WhatsApp / Signal / Email / 飞书 / 微信

```bash
hermes gateway run        # 启动
hermes gateway setup      # 配置
hermes gateway status     # 检查
```

**设计原则**: 同一Agent在多入口间共享Memory和Skills，保持一致性。

---

## 九、Token 与成本管理

### Token精简策略
1. **context_compression**: 自动压缩历史
2. **设置model.context_length**: 控制上下文窗口
3. **避免大段原文放prompt**: 用文件路径替代
4. **Skills用引用方式**: skill_view()而不是全文塞入

### 常用命令
```bash
hermes config set compression.enabled true
hermes config set compression.threshold 0.50
hermes config set compression.target_ratio 0.20
```

---

## 十、多Agent协作

### 方式A: delegate_task（轻量子代理）
```python
# 在会话中调用
delegate_task(
    goal="研究主题X",
    toolsets=["terminal", "file", "web"],
)
```

### 方式B: 独立Hermes进程（全功能）
```bash
hermes -w  # worktree模式，避免git冲突
```

### 方式C: 团队Kanban看板
```bash
hermes kanban init
hermes kanban create "任务标题"
hermes kanban assign <id>
```

Kanban 系统扩展指南（新增字段的完整 6 层链路）：`references/kanban-schema-extensions.md`

---

## 搜索后端配置

详见 `references/search-backends.md`：
- Tavily API Key 配置（`hermes config set` 正确写入 `.env`）
- SearXNG URL 配置（⚠️ `hermes config set` **会写入 config.yaml**，须手动移至 `.env`）
- SearXNG 测试（JSON API 通常被禁用 → 用 HTML + Python 解析）
- Tavily 测试（直接调用 API）
- 已知陷阱一览

## 常用排查命令速查

```bash
hermes doctor          # 健康检查
hermes doctor --fix    # 自动修复
hermes model           # 切换模型
hermes config show     # 查看配置
hermes status          # 组件状态
hermes sessions list   # 会话列表
hermes tools list      # 工具列表
hermes skills list     # 技能列表
hermes mcp list        # MCP列表
hermes cron list       # 定时任务
hermes plugins list    # 插件列表
hermes profile show    # 当前Profile
```
