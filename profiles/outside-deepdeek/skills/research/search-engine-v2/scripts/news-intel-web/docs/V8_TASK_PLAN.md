# News Platform V8 — Task Plan (Frozen)

## Decisions Confirmed

| # | Decision | Choice |
|:--:|------|------|
| 1 | VIP 付费墙 | ✅ 保留 (User.level free/vip/admin) |
| 2 | 广告 | ✅ 保留 (ads 表 + /ads 路由) |
| 3 | 鉴权范围 | Dashboard/Events 公开，/admin + 付费内容需登录 |
| 4 | PG 备份 | ✅ 已恢复, 18 tables, schema 完整 |
| 5 | article.category | P0 保留字符串, P5 改 FK |
| 6 | SQLite | 退出云端, PG 为唯一数据源 |
| 7 | SFTP | 废除, 统一 HTTP POST |

---

## P0 — Security + Foundation (2h)

### P0-1: 密钥迁移
- [ ] 创建 `.env` 文件，写入 `INTERNAL_TOKEN` 和 `JWT_SECRET`
- [ ] `routes/internal.py` 改读 `os.environ["INTERNAL_TOKEN"]`
- [ ] `routes/auth.py` 改读 `os.environ["JWT_SECRET"]`
- [ ] `.env` 加入 `.gitignore`
- [ ] 轮换新密钥值（旧值已公开）

**验收**: `grep -r "hermes-pipeline-secret-2026" api/` 返回空 | `grep -r "news-intel-secret-change-me" api/` 返回空

### P0-2: 数据库初始化
- [ ] 基于 pg_dump schema 创建 Alembic 初始迁移
- [ ] 补充新版表 (event_registry 字段扩展: SAO, evidence, source_chain, timeline JSONB)
- [ ] event.event_id 加唯一索引
- [ ] `alembic upgrade head` 验证通过

**验收**: `docker compose up postgres` → psql 连接 → 18 tables + 新版字段存在

---

## P1 — Backend Unification (3h)

### P1-1: 合并 FastAPI 路由
- [ ] 旧版 17 endpoints 迁移至 `apps/api/`
- [ ] 新版 6 endpoints 迁移至 `apps/api/`
- [ ] 统一 CORS 和错误处理
- [ ] 去掉 SQLite 依赖 (`db.py` 删除 sqlite3 import)

**验收**: 全部 23 endpoints 在 `/docs` 可见

### P1-2: 统一 Ingest
- [ ] `POST /internal/articles/batch` (已有，确认可用)
- [ ] `POST /internal/events/batch` (新增, 对齐 `_event_to_push_format()`)
- [ ] `event_article` 关联表写入逻辑

**验收**: curl POST 测试通过 → PG 查询有数据

### P1-3: 退休 SFTP
- [ ] `cron-sync.py` 删除 SFTP + SSH 段 (~30行)
- [ ] 改为调用 `pusher.push_events()`
- [ ] `pusher.py` 不改代码，仅确认 `NEWS_API_BASE` 指向新后端
- [ ] 删除 `sync-db-to-cloud.py`

**验收**: `cron-sync.py` 运行成功，无 paramiko 依赖，Dashboard 实时更新

---

## P2 — Auth System (2h)

### P2-1: 密码安全升级
- [ ] 安装 `passlib[bcrypt]`
- [ ] 替换 `hashlib.sha256` 为 `passlib.hash.bcrypt`
- [ ] 兼容旧哈希 (首次登录自动升级)

**验收**: 注册 → 登录 → token 有效

### P2-2: 鉴权中间件
- [ ] `/admin/*` 需要 JWT + admin role
- [ ] `/articles/*` VIP 内容需要 JWT (free 用户隐藏 content_md / analysis)
- [ ] `/api/v1/*` 公开 (Dashboard/Events/Sources 无需登录)
- [ ] `/internal/*` 需要 INTERNAL_TOKEN

**验收**: 无 token 访问 /admin → 403 | 访问 /api/v1/dashboard → 200

---

## P3 — Frontend Unification (6h)

### P3-1: 旧版页面移植
| 旧版页面 | 新版路由 | API | 认证 |
|---------|---------|-----|:--:|
| Home (热门+最新) | `/articles` | `/news/hot` + `/news/latest` | 公开 |
| Detail (文章详情) | `/articles/[id]` | `/news/{id}` | VIP content masked |
| Category | `/articles/category/[name]` | `/news?category=` | 公开 |
| Search | `/search` (合并) | 新版 `/search` + 旧版 `/news/search` | 公开 |
| Login | `/login` | `/auth/login` | 公开 |
| Admin | `/admin` | `/admin/dashboard` + CRUD | Admin |

**验收**: 6 pages 全部渲染真实 PG 数据

### P3-2: 统一组件库
- [ ] NewsCard 组件 (文章卡片, 替代 Vue NewsCard)
- [ ] 分级 Badge (tier A/B/C)
- [ ] 认证 Context (JWT token 管理)

**验收**: 组件在新旧页面均可复用

---

## P4 — Data Migration (1h)

- [ ] SQLite event_registry → PG events 表 (一次性)
- [ ] SQLite source_registry → PG sources 表
- [ ] SQLite entity_registry → PG entities 表
- [ ] 41 events + 19 sources + 18 entities 全部迁移

**验收**: PG `SELECT COUNT(*) FROM events` = 41

---

## P5 — Pipeline Config Page (3h)

### P5-1: 配置存储
- [ ] `pipeline_config` 表 (key TEXT, value JSONB, version INT, updated_at)
- [ ] 初始数据: source_scores.json, entity_weights.json, event_keywords.json, asset_graph.json
- [ ] 聚合阈值: MIN_SUBJECT_WEIGHT, HUB_RATIO, EVENT_THRESHOLD, MERGE_THRESHOLD

**验收**: PG 查询 `SELECT * FROM pipeline_config` 有数据

### P5-2: 配置页面
- [ ] `/admin/pipeline` 页面
- [ ] 评分模块: 4 个 JSON 编辑器
- [ ] 聚合模块: 4 个阈值滑块
- [ ] 保存 → 写入 PG → Pipeline 下次启动拉取
- [ ] Fallback: PG 不可用 → 本地文件

**验收**: 网页修改阈值 → Pipeline 重启 → 聚合结果变化

---

## P6 — Deploy & Cleanup (1h)

- [ ] 单 docker-compose.yml (postgres + backend + frontend + nginx)
- [ ] 端口统一 :80
- [ ] `.env` 模板 (不含真实密钥)
- [ ] 删除 `sync-db-to-cloud.py`
- [ ] 下线旧版 Vue.js 实例
- [ ] PG volume 持久化配置

**验收**: `docker compose up -d` → `curl localhost:80` → Dashboard 正常

---

## Summary

| Phase | Content | Hours | Depends On |
|-------|---------|:--:|------|
| P0 | Security + DB Foundation | 2h | — |
| P1 | Backend Unification + Ingest | 3h | P0 |
| P2 | Auth System | 2h | P1 |
| P3 | Frontend Unification | 6h | P1 |
| P4 | Data Migration | 1h | P1 |
| P5 | Pipeline Config Page | 3h | P3 |
| P6 | Deploy & Cleanup | 1h | All |
| **Total** | | **18h** | |
