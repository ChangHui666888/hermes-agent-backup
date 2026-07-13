# Architecture Gap Analysis: old vs new

## 1. 核心模型: Article → Event

| 维度 | news-intel-platform (旧) | Sentinel V1 (新) |
|------|--------------------------|-------------------|
| **数据单位** | Article (文章) | Event (事件) |
| **数据库** | PostgreSQL (SQLAlchemy ORM) | SQLite (raw SQL) |
| **表数量** | 11 tables + 6 associations | 6 tables (3 article + 3 event) |
| **关系** | Article → Source, Category, Tags, Ads, Users | Event ← aggregated from articles |
| **写入** | POST /internal/news/batch (Hermes推送) | aggregator.py 直接写入 SQLite |
| **读取** | SQLAlchemy query | sqlite3 raw SELECT + JSON 字段解析 |

**判断**: 旧版是"新闻 CMS"数据结构，新版是"事件情报"数据结构。新版的 Event Dossier (SAO + evidence + source_chain + timeline) 旧版完全没有。

## 2. 后端 API 对比

| 功能 | 旧版 | 新版 | Gap |
|------|:--:|:--:|:--:|
| 文章列表 | `/news?page=1` | ❌ | 新版不做文章级 |
| 文章详情 | `/news/{id}` | ❌ | 新版不做文章级 |
| 事件仪表盘 | ❌ | `/dashboard` | 新增 |
| 事件列表 | ❌ | `/events?filter` | 新增 |
| 事件档案 | ❌ | `/events/{id}` | 新增 |
| 来源网络 | ❌ | `/sources` | 新增 |
| 全文搜索 | ❌ | `/search?q=` | 新增 |
| 地图标记 | ❌ | `/map/events` | 新增 |
| 数据接收 | `/internal/news/batch` | ❌ | 新版读 SQLite 直连 |
| 用户认证 | `/auth` (JWT) | ❌ | 新版公开只读 |
| 后台管理 | `/admin` | ❌ | 无 |
| 广告管理 | `/ads` | ❌ | 无 |
| 分类浏览 | `/categories` | ❌ | 无 |

## 3. 前端页面对比

| 页面 | 旧版 (Vue.js) | 新版 (Next.js) | 状态 |
|------|:--:|:--:|:--:|
| 首页 | Home (热门+最新文章) | Dashboard (态势感知) | 完全不同 |
| 详情 | Detail (文章正文+AI分析) | Event Detail (事件档案6区) | 新版更强 |
| 列表 | ❌ 无事件列表 | Event Explorer (表格+筛选) | 新增 |
| 地图 | ❌ | Geo Monitor | 新增 |
| 来源 | ❌ | Source Network | 新增 |
| 搜索 | Search (简单) | Search (防抖全文) | 新版更强 |
| 分类 | Category (标签云) | ❌ | 缺失 |
| 登录 | Login | ❌ | 新版公开 |
| 后台 | Admin (统计+管理) | ❌ | 缺失 |

## 4. 部署架构

| 维度 | 旧版 | 新版 |
|------|------|------|
| 容器 | 3 (postgres + api + web) | 3 (nginx + backend + frontend) |
| Web 服务器 | nginx (Vite 静态) | nginx (Next.js proxy) |
| 数据库 | PostgreSQL (独立容器) | SQLite (volume mount) |
| 数据同步 | Hermes → POST /internal/news/batch | cron-sync.py → SCP + restart |
| 安全 | UFW + IP 白名单 | nginx only |
| 认证 | JWT token | 无 (公开只读) |

## 5. 功能 Gap 总结

### 新版有，旧版没有 (Sentinel 优势)

| 功能 | 描述 |
|------|------|
| **Event Dossier** | SAO + evidence + source_chain + timeline + AI intelligence |
| **态势感知 Dashboard** | Global Situation + World Map + Event Heat + Intel Feed |
| **事件聚合** | 2,404 文章 → 41 事件 (零 LLM) |
| **来源权威度** | source_registry + authority gauge |
| **信息流追踪** | break/follow source chain |
| **事件演化** | stage progress bar (breaking→developing→active→stable) |
| **事件筛选** | Topic + Stage + Country 三维筛选 |
| **地图分布** | Geo Monitor 520px |

### 旧版有，新版缺失 (可能需要的)

| 功能 | 旧版实现 | 建议 |
|------|---------|------|
| **管理后台** | /admin 统计面板 | Phase 2: 添加 pipeline 监控面板 |
| **用户系统** | JWT auth + 注册 | V1 不需要 (公开只读) |
| **分类浏览** | 标签云 + /category | 可加入 Event Explorer 侧栏 |
| **广告管理** | /ads CRUD | 不需要 |
| **文章级详情** | 正文渲染 + AI 分析卡片 | Event Detail 已包含 evidence |
| **数据推送接口** | POST /internal/news/batch | 新版直接读 SQLite |
| **数据库写模型** | PostgreSQL ORM | 不需要 (pipeline 直接写) |

## 6. 结论

```
旧版: Article CMS (面向内容管理)
     ├── 用户 + 权限 + 后台 + 广告
     └── 文章列表 → 文章详情 → AI 分析

新版: Event Intelligence Platform (面向情报分析)
     ├── 事件聚合 → 态势感知 → 情报档案
     └── 来源追踪 → 证据链 → 演化时间线
```

**核心 Gap**: 旧版缺少"事件"概念，新版缺少"管理"功能。两者定位完全不同 — 旧版是内容发布系统，新版是情报分析平台。V1 不需要补齐旧版功能。
