# Sentinel Intelligence — Web Operations Guide

> 版本: V1 | 部署: Docker Compose | 访问: http://100.107.117.23

## 架构

```
                    http://100.107.117.23
                           │
                      Nginx (:80)
                      reverse proxy
                           │
            ┌──────────────┴──────────────┐
            │                             │
       /api/*                         /*
            │                             │
      FastAPI (:8000)              Next.js (:3000)
      Python 3.12                  Node 22 Alpine
            │                             │
      SQLite read-only             6 pages, 15 components
      /data/news_intel.db
            │
      Docker volume mount
      ./data/news_intel.db (host)
```

## 页面导航

| 页面 | URL | 用途 |
|------|-----|------|
| Situation | `/` | 全球态势感知：统计 + 地图 + 热力 + 情报流 |
| Event Detail | `/events/EVT-...` | 事件档案：事实 → 证据 → 演化 → 信息流 → AI 分析 |
| Event Explorer | `/events` | 筛选表格：Topic / Stage / Country + 分页 |
| Geo Monitor | `/map` | 世界地图事件分布 (520px 大屏) |
| Source Network | `/sources` | 来源权威度排行 + 事件覆盖统计 |
| Search | `/search` | 防抖全文搜索 (标题/摘要/关键词) |

## 部署操作

### 启动

```bash
ssh administrator@100.107.117.23
cd /home/administrator/news-intel-web
docker compose up -d
```

### 查看状态

```bash
docker compose ps
# 期望: backend UP (healthy), frontend UP, nginx UP
```

### 重启

```bash
docker compose restart          # 全部
docker compose restart backend  # 仅后端 (换 DB 后)
docker compose restart frontend # 仅前端 (代码更新后)
docker compose restart nginx    # 仅 nginx (502 时)
```

### 更新代码后重新部署

```bash
# 本地推送
cd search-engine-v2/scripts
python sync-db-to-cloud.py       # 上传 DB
git push

# 云端拉取重建
ssh administrator@100.107.117.23
cd /home/administrator/news-intel-web
git pull
docker compose up -d --build
docker compose restart nginx
```

### 停止

```bash
docker compose down
```

## 监控

### API 健康检查

```bash
# 从云端
curl localhost:80/api/v1/dashboard | python3 -c "import sys,json; print(json.load(sys.stdin)['metrics'])"

# 从本地
curl http://100.107.117.23/api/v1/dashboard
```

### 容器状态

```bash
docker compose ps
docker compose logs backend --tail=20
docker compose logs frontend --tail=20
```

### 数据同步检查

```bash
# 本地
python -c "import sqlite3; c=sqlite3.connect('news_intel/news_intel.db'); print(c.execute('SELECT COUNT(*) FROM event_registry').fetchone()[0])"

# 云端
curl http://100.107.117.23/api/v1/dashboard | python3 -c "import sys,json; print(json.load(sys.stdin)['metrics']['active_events'])"

# 两边数字应一致 (当前: 41)
```

## 故障排查

| 症状 | 原因 | 修复 |
|------|------|------|
| 502 Bad Gateway | Nginx 缓存旧 upstream | `docker compose restart nginx` |
| API unavailable (前端) | 后端未启动 | `docker compose restart backend` |
| Internal Server Error (API) | DB 文件不可读 | 检查 `/data/news_intel.db` 挂载 |
| 数据不一致 | 同步未执行 | `python sync-db-to-cloud.py` |
| 无法访问 | 云主机宕机 | 重启云主机 → `docker compose up -d` |
| 页面空白 (空架子) | 前端 fetch 失败 | 检查 `api.ts` 的 API_BASE |

## 自动化

| 任务 | 方式 | 频率 | 状态 |
|------|------|:--:|:--:|
| 数据同步 | Hermes Cron `db-cloud-sync` (92b78fee7369) | 30min | ✅ |
| Web 服务 | Docker `restart: unless-stopped` | 持续 | ✅ |

手动触发同步：

```bash
cd search-engine-v2/scripts
python sync-db-to-cloud.py
```

## 常用命令速查

```bash
# 一键状态检查 (云端)
cd /home/administrator/news-intel-web
docker compose ps
curl -s localhost:80/api/v1/dashboard | python3 -c "import sys,json; print(json.load(sys.stdin)['metrics'])"

# 一键重建前端 (云端)
docker compose up -d --build frontend && docker compose restart nginx

# 一键同步 DB (本地)
python sync-db-to-cloud.py
```
