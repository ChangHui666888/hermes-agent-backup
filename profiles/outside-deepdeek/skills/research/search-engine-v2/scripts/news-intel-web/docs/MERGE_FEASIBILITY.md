# Merge Feasibility: Old Platform + Sentinel V1 → Unified Instance

## 1. 旧版完整 API 清单

| 路由 | 方法 | 功能 | 数据源 | 认证 |
|------|:--:|------|------|:--:|
| `/news` | GET | 文章列表 (分页/分类/标签/分级) | PG | 可选 JWT |
| `/news/{id}` | GET | 文章详情 (正文+AI分析) | PG | 可选 |
| `/news/hot` | GET | 热门文章 (Top N) | PG | 否 |
| `/news/latest` | GET | 最新文章 | PG | 否 |
| `/news/search` | GET | 文章搜索 | PG | 否 |
| `/internal/news/batch` | POST | Hermes 推送批量入库 | PG | Token |
| `/auth/login` | POST | 邮箱+密码登录 | PG | 否 |
| `/auth/register` | POST | 用户注册 | PG | 否 |
| `/auth/me` | GET | 当前用户信息 | PG | JWT |
| `/auth/subscribe` | POST | 订阅管理 | PG | JWT |
| `/admin/dashboard` | GET | 后台统计 (文章/用户/广告) | PG | Admin |
| `/admin/articles` | GET | 文章管理列表 | PG | Admin |
| `/admin/articles/{id}` | PUT | 编辑文章 | PG | Admin |
| `/admin/ads` | CRUD | 广告管理 | PG | Admin |
| `/admin/users` | GET | 用户管理 | PG | Admin |
| `/ads/random` | GET | 随机广告 | PG | 否 |
| `/categories` | GET | 分类及文章数 | PG | 否 |

**17 个端点**，数据全部来自 PostgreSQL。

## 2. 新版完整 API 清单

| 路由 | 方法 | 功能 | 数据源 |
|------|:--:|------|------|
| `/api/v1/dashboard` | GET | 态势感知 (KPI+热点+地图) | SQLite |
| `/api/v1/events` | GET | 事件列表 (分页/筛选) | SQLite |
| `/api/v1/events/{id}` | GET | 事件档案 (完整 Dossier) | SQLite |
| `/api/v1/sources` | GET | 来源网络 (权威度+覆盖) | SQLite |
| `/api/v1/search` | GET | 全文搜索 (标题/摘要/关键词) | SQLite |
| `/api/v1/map/events` | GET | 地理标记点 | SQLite |

**6 个端点**，数据全部来自 SQLite。公开只读，无认证。

## 3. 旧版前端完整清单

| 页面 | 路由 | 组件 | API 调用 |
|------|------|------|------|
| Home | `/` | NavBar + NewsCard | `/news/hot` + `/news/latest` + `/categories` |
| Detail | `/news/:id` | NavBar + 正文渲染 + AI分析 | `/news/{id}` |
| Search | `/search` | NavBar + NewsCard + 分页 | `/news/search?q=` |
| Category | `/category/:name` | NavBar + NewsCard | `/news?category=` |
| Login | `/login` | 表单 | `/auth/login` |
| Admin | `/admin` | 统计卡片 + 表格 | `/admin/dashboard` + CRUD |

**6 个页面，2 个共享组件** (NavBar, NewsCard)，Vue.js + Vite。

## 4. 新版前端完整清单

| 页面 | 路由 | API 调用 |
|------|------|------|
| Situation | `/` | `/api/v1/dashboard` |
| Event Detail | `/events/{id}` | `/api/v1/events/{id}` |
| Event Explorer | `/events` | `/api/v1/events?filters` |
| Geo Monitor | `/map` | `/api/v1/map/events` |
| Source Network | `/sources` | `/api/v1/sources` |
| Search | `/search` | `/api/v1/search?q=` |

**6 个页面，15 个组件**，Next.js 16 + React。

## 5. 合并映射

### 后端合并 (33 endpoints total)

```
合并后 FastAPI:

━━ 旧版路由 (PG) ━━━━━━━━━━━━━━━━━━ 新版路由 (SQLite) ━━━━━━
/news, /news/{id}                   /api/v1/dashboard
/news/hot, /news/latest            /api/v1/events
/news/search                        /api/v1/events/{id}
/internal/news/batch                /api/v1/sources
/auth/*                             /api/v1/search
/admin/*                            /api/v1/map/events
/ads/random
/categories
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         PostgreSQL                    SQLite
    (SQLAlchemy ORM)              (sqlite3 raw)
```

### 前端页面合并 (10 pages total)

```
合并后 Next.js:

━━ 旧版页面 (移植) ━━━━━━━━━━━━━━ 新版页面 (保留) ━━━━━━━━
/articles               ← /news        /              Situation
/articles/[id]          ← /news/:id    /events/[id]   Event Detail
/articles/search        ← /search      /events        Explorer
/articles/category/[name] ← /category  /map           Geo
/login                  ← /login       /sources       Source Network
/admin                  ← /admin       /search        Search
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
             6 pages to port               6 pages existing
```

## 6. Docker 合并

```
合并前 (双实例, 6 containers):         合并后 (单实例, 4 containers):
                                   
Sentinel:                             Unified:
  nginx (80)                           nginx (80)
  frontend (3000)                      frontend (3000)
  backend (8000)                       backend (8000)
                                       postgres (5432)
Old Platform:                         
  nginx-web (80→不用)                  ports: 80 only
  api (8001)
  postgres (5432)
```

## 7. 工作量重新评估

| # | 任务 | 工时 |
|:--:|------|:--:|
| 1 | 后端合并: 旧版 17 endpoints + 新版 6 → 同一 FastAPI | 1h |
| 2 | 双数据源: PostgreSQL (SQLAlchemy) + SQLite (raw) 共存 | 0.5h |
| 3 | 移植 Article 列表页 (替代旧版 Home) | 2h |
| 4 | 移植 Article 详情页 (替代旧版 Detail) | 2h |
| 5 | 移植 Admin 后台页 | 3h |
| 6 | 移植 Login 页 | 1h |
| 7 | 移植 Category 页 | 1h |
| 8 | Docker: 单 compose 文件 | 0.5h |
| 9 | 测试验证 | 2h |
| **总计** | | **13h** |

## 8. 结论

```
✅ 可行: 统一 FastAPI + 统一 Next.js + 单端口 80

合并后架构:
  http://100.107.117.23
    ├── /                    Sentinel Dashboard (新版)
    ├── /events/*            Event Explorer + Detail (新版)
    ├── /map                 Geo Monitor (新版)
    ├── /sources             Source Network (新版)
    ├── /search              Unified Search (新版+旧版)
    ├── /articles            Article List (旧版移植)
    ├── /articles/[id]       Article Detail (旧版移植)
    ├── /articles/category/* Category (旧版移植)
    ├── /login               Login (旧版移植)
    └── /admin               Admin Dashboard (旧版移植)

数据:
  └── PostgreSQL (articles, users, ads) + SQLite (events, sources)
```
