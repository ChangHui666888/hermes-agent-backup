# Sentinel Intelligence

基于 v4.4 Event Dossier 的事件情报驾驶舱。

## 架构

```
本地 Windows (Hermes)                    云 Ubuntu (Docker)
─────────────────────                    ─────────────────────
RSS Scanner (70源)                        ┌────────────────┐
    ↓                                     │   Nginx (:80)   │
Score + Fetch + Aggregate v4.4            └───────┬────────┘
    ↓                                     ┌───────┴────────┐
Event Registry (SQLite)                   │  Next.js 16     │
    ↓                                     │  Dashboard ·     │
    │  read-only mount                    │  Detail ·        │
    │                                     │  Explorer ·      │
    └─────────── 共享卷 ──────────────────│  Geo · Sources · │
                                          │  Search          │
                                          └───────┬────────┘
                                          ┌───────┴────────┐
                                          │  FastAPI (8000) │
                                          │  6 endpoints    │
                                          └────────────────┘
```

## 页面

| 页面 | 路由 | 职责 |
|------|------|------|
| Situation | `/` | 全球态势感知：地图 + 热力 + 情报流 |
| Event Detail | `/events/[id]` | 事件档案：事实 → 证据 → 演化 → 信息流 |
| Event Explorer | `/events` | 筛选表格：Topic / Stage / Country |
| Geo Monitor | `/map` | 地理事件分布 |
| Source Network | `/sources` | 来源权威度 + 事件覆盖 |
| Search | `/search` | 防抖全文搜索 |

## 快速开始

```bash
# 云端部署
cd /home/administrator/news-intel-web
docker compose up -d

# 查看状态
docker compose ps
curl localhost/api/v1/dashboard

# 本地 Pipeline 推送 (Windows)
cd search-engine-v2/scripts
python test_aggregator.py --hours 24 --window 6
```

## 目录

```
news-intel-web/
├── frontend/           Next.js 16 + Tailwind 4
│   ├── src/app/        6 页面路由
│   ├── src/components/ 15 组件
│   │   ├── layout/     Header + Sidebar
│   │   ├── dashboard/  WorldMap / EventHeat / IntelFeed
│   │   ├── event/      EventCard / FactPanel / Timeline / Evidence / SourceChain / Intelligence
│   │   └── common/     Badge
│   ├── Dockerfile      node:22-alpine multi-stage
│   └── next.config.ts
├── backend/            FastAPI Read Adapter
│   ├── main.py         6 API endpoints
│   ├── db.py           SQLite immutable read-only
│   ├── Dockerfile      python:3.12-slim
│   └── api/            dashboard / events / map / sources / search
├── docker-compose.yml  frontend + backend + nginx
├── nginx.conf          reverse proxy
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DATA_FLOW.md
│   ├── DEPLOYMENT.md
│   └── V1_ACCEPTANCE.md
└── README.md
```
