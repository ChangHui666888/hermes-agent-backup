---
name: content-factory
description: 13 节点自媒体内容生产工业级平台，基于 Hermes Agent delegate_task 构建
version: 1.1.0
author: Content Factory
---

# Content Factory - 自媒体内容生产工业级平台

一个 13 节点 DAG 工作流引擎，基于 Hermes Agent 构建，覆盖自媒体内容从选题到归档学习的完整生产流程。包含 CLI 工具和 Web Dashboard。

## 访问入口

| 地址 | 用途 |
|------|------|
| `http://localhost:8650/` | **Content Factory Dashboard** (FastAPI + Vue SPA) |
| `http://localhost:8648/` | Hermes Studio (Hermes 官方管理界面) |

## 架构

```
~/content-factory/
├── content_engine/          # 核心引擎
│   ├── dag.py               # DAG 编排器（拓扑排序 + 节点调度）
│   ├── models.py            # 13 节点 Pydantic 数据模型
│   ├── store.py             # SQLite 持久层
│   ├── cli.py               # CLI 交互界面
│   ├── webui.py             # FastAPI Web Dashboard
│   ├── agents/              # Hermes 子代理集成层
│   └── nodes/               # 13 个节点实现
├── content_data/            # 运行时数据 (SQLite)
│   └── content_factory.db
├── hermes_skills/           # Hermes Skills 注册
└── scripts/cf.sh            # 入口脚本
```

## 13 节点 DAG 流程

```
[1.选题发现] → [2.评分筛选] → [3.策略设计] ⇄ [4.素材收集]
       ↓                              ↓
       └───────── 协同小循环 ─────────┘
                          ↓
                  [5.内容结构] → [6.多版本生成] → [7.AI评审]
                          ↓
                  [8.人工审核 Gate] → [9.平台适配] → [10.发布执行]
                          ↓
                [11.数据采集] → [12.内容归档] → [13.策略学习]
                          ↓
              回流至 [1] / [3]
```

## 快速追热通道

`trend_score > 90` 且生命周期 < 6h 时自动走简化路径：
`[1] → [2] → [6] → [8] → [10] → [11] → [12] → [13]`

## CLI 命令

```bash
export PYTHONPATH="$HOME/content-factory:$PYTHONPATH"
cd ~/content-factory

python -m content_engine.cli discover "标题" [趋势分]   # 标准流程
python -m content_engine.cli quick "热点标题"            # 快速通道
python -m content_engine.cli list                        # 管道列表
python -m content_engine.cli show <id>                   # 管道详情
python -m content_engine.cli archive list|hits           # 归档/爆款
python -m content_engine.cli install-skills              # 注册 Skills

# 启动 Web Dashboard
python -m content_engine.webui                           # 访问 http://localhost:8650/
```

## Hermes Agent 集成

AI 密集型节点通过 `_call_agent()` 占位，可供 `delegate_task` 调用。
Skills 注册在 `~/content-factory/hermes_skills/`：
`content-factory-topic_discovery`, `-scoring`, `-strategy`, `-materials`, `-outline`, `-generation`, `-review`, `-adaptation`, `-learning`

## 三阶段合规过滤

1. 选题时初筛风险（灰标 gray）
2. 素材时检查信源合法性（多源交叉验证）
3. 发布前终审事实与法律合规（人工 Gate）

## 人机回环 HITL

- AI推荐 → 人确认选题优先级
- AI生成多版本 → 人选择或融合
- AI事实核查 → 人最终签批
- AI提取规律 → 人复盘判断
