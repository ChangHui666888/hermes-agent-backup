# Profile Analysis — outside-deepdeek

## 1. Workspace 脚本

```
workspace/
├── scrapling_wsj.py         WSJ 反爬测试 (patchright Playwright)
├── scrapling_wsj2.py        WSJ 反爬测试 (Scrapling StealthyFetcher)
├── test_direct_extract.py   三级抓取测试 (web_extract → Scrapling → Wayback)
├── real_demo.py             真实 Hermes 工具替换 Mock 搜索→抽取
└── exec_code_workaround.py  terminal 模拟 execute_code

结论: 全部是 WSJ 反爬实验脚本，非生产代码。可清理。
```

## 2. 项目全景

```
outside-deepdeek/
│
├── scripts/                          ← 运维脚本
│   ├── cron-sync.py                  ← 聚合 + 云端同步
│   └── sync-db-to-cloud.py           ← SCP 上传 SQLite
│
├── skills/research/search-engine-v2/ ← 主项目
│   └── scripts/
│       ├── news_intel/               ← Pipeline 数据生产 (核心)
│       │   ├── aggregator.py         L5 事件聚合 (41 events)
│       │   ├── db.py                 6 表 SQLite (2,404 文章)
│       │   ├── scorer.py             L1 五维评分
│       │   ├── batch.py + fetchers   L2 全文抓取
│       │   ├── enhancers.py          L4 三级增强 (Qwen3/DeepSeek)
│       │   ├── pipeline.py           主编排入口
│       │   ├── pusher.py             → 云端推送
│       │   └── generator.py          L9 洞察生成
│       │
│       ├── news-intel-platform/      ← 旧版 Web (已冻结)
│       │   ├── api/                  FastAPI + PostgreSQL
│       │   └── web/                  Vue.js + Vite
│       │
│       ├── news-intel-web/           ← Sentinel V1 (当前生产)
│       │   ├── frontend/             Next.js 16 (6 pages)
│       │   ├── backend/              FastAPI (6 endpoints)
│       │   ├── docker-compose.yml
│       │   └── docs/                 5 份文档
│       │
│       ├── cron-sync.py              聚合 + 云端同步脚本
│       ├── sync-db-to-cloud.py       云端 DB 推送
│       ├── core/                     cascade/fetchers/temporal/extractor
│       ├── config/                   domain_profiles/settings
│       └── skills/                   s01-s07 纯逻辑模块
│
├── skills/software-development/      ← 技能积累
│   ├── web-intelligence-dashboard/
│   └── intelligence-dashboard/
│
├── skills/devops/                    ← 部署技能
│   ├── docker-web-deployment/
│   ├── web-docker-deploy/
│   └── hermes-cron-engineering/
│
├── cron/                             ← 定时任务
│   └── jobs.json                     db-cloud-sync (30min)
│
├── wiki/                             ← 知识库 (C:\Users\ChangHui\wiki)
│
└── memories/                         ← 会话记忆
```

## 3. 架构总图

```
┌─────────────────────────────────────────────────────────────┐
│                    OUTSIDE-DEEPDEEK PROFILE                  │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ news_intel   │  │ news-intel-  │  │ news-intel-web   │  │
│  │ Pipeline     │  │ platform     │  │ Sentinel V1      │  │
│  │ (数据生产)    │  │ (旧版·冻结)  │  │ (当前生产)        │  │
│  │              │  │              │  │                  │  │
│  │ L1-L5 规则    │  │ Vue.js+PG    │  │ Next.js 16       │  │
│  │ 2,404→41     │  │ 已下线       │  │ FastAPI+SQLite   │  │
│  │ ↓            │  │              │  │ Docker Cloud     │  │
│  │ SQLite       │  │              │  │ :80 对外         │  │
│  └──────┬───────┘  └──────────────┘  └────────┬─────────┘  │
│         │                                      │            │
│         │         cron-sync.py (30min)          │            │
│         └──────────────────────────────────────┘            │
│                       SCP + restart                         │
│                          │                                  │
└──────────────────────────┼──────────────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │ Cloud VPS   │
                    │ Docker      │
                    │ :80 Web     │
                    └─────────────┘
```

## 4. 优化建议

| # | 问题 | 建议 | 优先级 |
|:--:|------|------|:--:|
| 1 | `workspace/` 5 个 WSJ 实验脚本 | 删除或移至 `tests/` | Low |
| 2 | `news-intel-platform/` 旧版仍占空间 | 确认不再需要后归档 | Low |
| 3 | `search-engine-v2.rar` 159MB 二进制 | 已在 .gitignore, 确保不提交 | High |
| 4 | `frontend/node_modules/` 在 Git 中 | 确保 .gitignore 排除 | High |
| 5 | `cron/jobs.json` 每次运行更新 | 加入 .gitignore 或采用状态文件分离 | Medium |
| 6 | `skills/` 26 个家族, 部分未使用 | 定期清理未用 skill | Low |
| 7 | `scripts/` 中有两份 cron-sync (profile级 + project级) | 统一为一份 | Medium |
| 8 | `cache/terminal/` 积累快照文件 | 定期清理 | Low |
