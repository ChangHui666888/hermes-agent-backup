# Sentinel Intelligence V8 — 部署运维手册

## 仓库

| 仓库 | URL | 用途 |
|------|-----|------|
| 主仓库 | `https://github.com/ChangHui666888/hermes-agent-backup` | Pipeline + Web 完整代码 |
| Web 独立 | `https://github.com/ChangHui666888/sentinel-intelligence` | Web V1 快照 |

## 架构

```
                    http://100.107.117.23
                           │
                    Nginx (:80)
                    reverse proxy
                           │
            ┌──────────────┼──────────────┐
            │              │              │
         /api/*          /news/*          /*
         /auth/*         /admin/*      Next.js (:3000)
         /internal/*     /ads/*        12 pages
            │              │         15 components
            └──────┬───────┘
                   │
            FastAPI (:8000)
            23 endpoints
                   │
            PostgreSQL (:5432)
            events(41) + articles(160)
            sources(24) + users(3)
```

## 目录

```
search-engine-v2/scripts/
├── news_intel/              Pipeline 数据生产 (v4.4)
│   ├── aggregator.py        事件聚合 (零LLM)
│   ├── scorer.py            五维评分
│   ├── batch.py             全文抓取
│   ├── enhancers.py         三级增强
│   ├── pipeline.py          主编排
│   ├── db.py                6表 SQLite
│   └── news_intel.db        本地数据库
│
├── news-platform-v8/        统一平台 (V8)
│   ├── docker-compose.yml   4 容器编排
│   ├── Dockerfile.backend   后端镜像
│   ├── nginx.conf           反向代理
│   ├── apps/api/            后端源码
│   │   ├── main.py          入口 (23 routes)
│   │   ├── database.py      PostgreSQL 连接
│   │   ├── models.py        18 tables
│   │   ├── schemas.py       Pydantic
│   │   └── routes/          12 路由文件
│   │       ├── news.py         文章CRUD
│   │       ├── internal.py     数据接收
│   │       ├── auth.py         认证 (bcrypt+JWT)
│   │       ├── admin.py        后台管理
│   │       ├── ads.py          广告
│   │       ├── categories.py   分类
│   │       ├── admin_config.py 配置管理
│   │       ├── dashboard_v1.py Sentinel仪表盘
│   │       ├── events_v1.py    事件查询
│   │       ├── sources_v1.py   来源网络
│   │       ├── search_v1.py    搜索
│   │       └── map_v1.py       地图
│   ├── frontend/            前端源码 (Next.js 16)
│   │   └── src/app/         12 页面
│   └── docs/                10 份文档
│
├── news-intel-platform/     旧版 (已冻结)
├── cron-sync.py             定时同步 (HTTP, 无SFTP)
└── migrate_events.py        SQLite→PG 迁移工具
```

## 部署

### 首次部署

```bash
# 云端
cd /home/administrator/news-platform-v8
docker compose up -d --build
```

### 日常更新

```bash
# 本地推送
git add -A && git commit -m "update" && git push

# 云端拉取重建
ssh administrator@100.107.117.23
cd /home/administrator/news-platform-v8
git pull
docker compose up -d --build
```

### 状态检查

```bash
docker compose ps
curl localhost:80/api/v1/dashboard
```

### 数据同步

```bash
# 本地 Pipeline → 云端
python cron-sync.py
# 或 Hermes cron: db-cloud-sync (30min)
```

## 监控

```bash
# API 健康
curl http://100.107.117.23/api/v1/dashboard
# → {"metrics": {"active_events": 41, "sources": 24}}

# 容器状态
docker compose ps
# → 4 services UP

# 数据库
docker exec news-platform-v8-postgres-1 psql -U news_admin -d news_intel -c "SELECT count(*) FROM events"
```

## 故障排查

| 症状 | 修复 |
|------|------|
| 502 Bad Gateway | `docker compose restart nginx` |
| 500 Internal Server | `docker compose logs backend --tail=20` |
| 数据不更新 | `python cron-sync.py` |
| 容器全部 Down | `docker compose up -d` |

## 账号

```
管理员: admin@test.com / admin123
API Token: v8-pipeline-token-2026-xK9mP2sR7wQ (环境变量 INTERNAL_TOKEN)
```

## 数据流

```
RSS (70源) → Scorer → Fetcher → Aggregator → SQLite (本地)
                                                  │
                                          cron-sync.py (HTTP POST)
                                                  │
                                          PostgreSQL (云端)
                                                  │
                                          FastAPI + Next.js → Web
```
