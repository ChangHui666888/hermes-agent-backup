# News Intelligence Platform — Web V1 开发任务清单 (已冻结)

## 冻结声明

> 基于已有 news_intel v4.4 Event Dossier 数据，开发 Web Intelligence Dashboard V1。
> **禁止修改数据生产链**，只建设展示和查询层。
> 本阶段目标：验证"信息 → 事件 → 情报展示"闭环，不是做新闻网站。

## 验证结果 (2026-07-12)

event_registry 10/10 关键字段全部就绪：
event_id / title / summary / confidence / last_updated ✅
source_chain (role break/follow) / url ✅
timeline (time + update) ✅
evidence (quote + source) ✅

## 技术栈决定 (已冻结)

- Backend: FastAPI (Python, **只读** SQLite event_registry — 不做 PostgreSQL 迁移)
- Frontend: Next.js 14 (App Router) + Tailwind CSS + shadcn/ui
- Database: SQLite event_registry 直接读取 (v4.4 pipeline 写入的生产库)
- API Adapter: FastAPI Serializer 层 — 将 event_registry 字段映射为 Web JSON
- 项目路径: ~/workspace/news-intel-web/

## 项目结构

```
~/workspace/news-intel-web/
├── backend/
│   ├── main.py          # FastAPI app entry
│   ├── api/
│   │   ├── dashboard.py # GET /api/v1/dashboard
│   │   ├── events.py    # GET /api/v1/events, GET /api/v1/events/{id}
│   │   ├── sources.py   # GET /api/v1/sources
│   │   ├── search.py    # GET /api/v1/search
│   │   └── ingest.py    # POST /internal/events/batch (receive from pusher)
│   ├── models/
│   │   └── schemas.py   # Pydantic models
│   ├── db.py            # SQLite direct read + PostgreSQL write
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           # Dashboard
│   │   │   ├── events/
│   │   │   │   ├── page.tsx       # Explorer
│   │   │   │   └── [id]/
│   │   │   │       └── page.tsx   # Detail
│   │   │   ├── sources/
│   │   │   │   └── page.tsx
│   │   │   └── search/
│   │   │       └── page.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   └── Sidebar.tsx
│   │   │   ├── dashboard/
│   │   │   │   ├── MetricCard.tsx
│   │   │   │   ├── EventGrid.tsx
│   │   │   │   └── EventStream.tsx
│   │   │   ├── event/
│   │   │   │   ├── EventCard.tsx
│   │   │   │   ├── EventHeader.tsx
│   │   │   │   ├── FactPanel.tsx
│   │   │   │   ├── Timeline.tsx
│   │   │   │   ├── SourceChain.tsx
│   │   │   │   ├── EvidenceCard.tsx
│   │   │   │   └── IntelligencePanel.tsx
│   │   │   ├── common/
│   │   │   │   ├── Badge.tsx
│   │   │   │   ├── StatusDot.tsx
│   │   │   │   ├── SearchBox.tsx
│   │   │   │   └── Table.tsx
│   │   │   └── ui/              # shadcn/ui components
│   │   ├── lib/
│   │   │   ├── api.ts           # API client
│   │   │   └── types.ts         # TypeScript types
│   │   └── styles/
│   │       └── globals.css      # Dark theme tokens
│   ├── tailwind.config.ts
│   ├── next.config.js
│   └── package.json
└── README.md
```

## API Contract (冻结 — 前后端共同语言)

在 frontend/src/contracts/ 目录下定义 TypeScript 接口，与 FastAPI Pydantic models 一一对应：

### contracts/event.ts
```typescript
export interface EventDossier {
  event_id: string;
  title: string;
  summary: string;
  event_type: string;
  stage: 'breaking' | 'developing' | 'active' | 'stable' | 'closed';
  confidence: number;
  coherence: number;
  subject: { entity_id: string; name: string; type: string };
  action: { type: string; detail: string };
  object: { entity_id: string; name: string; type: string };
  location: { country: string | null; region: string | null };
  source: {
    primary_source: string;
    primary_source_id: string;
    authority: number;
    source_count: number;
    sources: string[];
  };
  actors: { entity: string; type: string; role: 'Initiator' | 'Target' | 'Participant' }[];
  keywords: string[];
  related_entities: { entity_id: string; name: string; type: string }[];
  article_count: number;
  first_seen: string | null;
  last_updated: string | null;
  evidence: { quote: string; source: string; url: string }[];
  source_chain: { source_id: string; source_name: string; time: string; role: 'break' | 'follow'; url: string }[];
  timeline: { time: string; update: string; source: string }[];
  llm_analysis: Record<string, any> | null;
}
```

### contracts/dashboard.ts
```typescript
export interface DashboardMetrics {
  active_events: number;
  critical_events: number;
  today_updates: number;
  sources: number;
}

export interface DashboardResponse {
  metrics: DashboardMetrics;
  hot_events: EventDossier[];
  map_events: MapEvent[];
}

export interface MapEvent {
  event_id: string;
  title: string;
  country: string | null;
  impact_level: string;
  confidence: number;
}
```

### contracts/source.ts
```typescript
export interface SourceEntity {
  source_id: string;
  name: string;
  type: 'MEDIA' | 'GOVERNMENT' | 'RESEARCH' | 'SOCIAL';
  authority: number;
  event_count: number;
}
```

## API 端点列表 (冻结 — 6 endpoints)

| Endpoint | 用途 | 数据来源 |
|----------|------|----------|
| GET /api/v1/dashboard | KPI + hot_events + map_events | event_registry |
| GET /api/v1/events | 分页列表 + 筛选 (topic/country/impact) | event_registry |
| GET /api/v1/events/{event_id} | 完整 Event Dossier | event_registry |
| GET /api/v1/sources | 来源注册表 | source_registry + 聚合 |
| GET /api/v1/search?q= | 全文搜索 | event_registry title+summary |
| GET /api/v1/map/events | 地图标记点 | event_registry (country非空) |

## 开发任务 (8 tasks, 冻结顺序)

```
Task-001  初始化 + Design System + API Contract
     ↓
Task-002  Layout + Routing    +    Task-003  FastAPI Read Adapter
     ↓                                  ↓
Task-005  Event Dossier Detail ⭐⭐⭐ (核心验收)
     ↓
Task-004  Dashboard + Global Event Map
     ↓
Task-006  Event Explorer
     ↓
Task-007  Source Explorer + Search
     ↓
Task-008  UI Polish + QA
```

### Task-001: 初始化项目 + Design System + API Contract

**输入**: 无
**输出**: 
- `backend/main.py` FastAPI 启动成功 (uvicorn, port 8000)
- `frontend/` Next.js 启动成功 (npm run dev, port 3000)
- `frontend/src/contracts/event.ts`, `dashboard.ts`, `source.ts` API Contract 就位
- Dark Intelligence Theme CSS tokens 就位
- shadcn/ui 组件库安装完成

**验收**:
```bash
cd backend && uvicorn main:app --port 8000  # -> 200 OK /docs
cd frontend && npm run dev                    # -> localhost:3000 显示 Dark Theme 空白页
```
- contracts/ 目录下 3 个 TypeScript 接口文件通过 `tsc --noEmit` 检查

**详细步骤**:
1. 创建 `~/workspace/news-intel-web/` 目录结构
2. 初始化 FastAPI backend with cors, 路由骨架
3. `npx create-next-app@latest frontend --typescript --tailwind --app`
4. 安装 shadcn/ui: `npx shadcn-ui@latest init` (style: new-york, base: slate)
5. 创建 `frontend/src/contracts/event.ts`, `dashboard.ts`, `source.ts` — 冻结 API Contract
6. 配置 Dark Intelligence Theme CSS tokens:
   ```css
   :root {
     --bg-primary: #080B12; --bg-secondary: #111827; --bg-card: #151B26;
     --text-primary: #F8FAFC; --text-secondary: #94A3B8; --text-muted: #64748B;
     --status-critical: #EF4444; --status-high: #F97316; --status-medium: #EAB308; --status-low: #22C55E;
   }
   ```
7. Tailwind config: extend colors with above tokens
8. 验证双端可运行

---

### Task-002: Layout (Header + Sidebar) + 页面路由骨架

**输入**: Task-001 完成
**输出**:
- Header 组件: Logo "NEWS INTELLIGENCE" + SearchBox + UTC时钟
- Sidebar 组件: RADAR/Dashboard, EVENTS/Explorer, SOURCES/Registry, TOOLS/Search + Pipeline状态指示
- 5个页面路由骨架 (Dashboard, Events, Event/[id], Sources, Search)

**验收**:
- 页面显示 Header + Sidebar 布局
- 点击 Sidebar 菜单项切换页面 (Dashboard ↔ Events ↔ Sources ↔ Search)
- Active 菜单项高亮蓝色 (#1D4ED8)
- Header UTC 时钟实时更新

**详细步骤**:
1. 创建 `layout/Header.tsx`: 64px高, flex布局, Logo左, SearchBox中, UTC右
2. 创建 `layout/Sidebar.tsx`: 240px宽, flex-col, 4段菜单 + 底部 Pipeline 状态
3. 创建 `app/layout.tsx`: Header + Sidebar + Content 三栏布局
4. 创建 5个页面占位: Dashboard(实时事件), Events(表格), Event/[id](详情), Sources(卡片), Search(搜索)
5. 用 next/navigation usePathname 实现 Active 菜单状态
6. UTC 时钟用 useEffect + setInterval 每秒更新

---

### Task-003: FastAPI Read Adapter (SQLite only)

**输入**: Task-001 backend 可运行
**输出**: 6个 API endpoint 全部可用，返回真实 event_registry 数据 (SQLite 只读直连)

| Endpoint | 用途 | 数据来源 |
|----------|------|----------|
| GET /api/v1/dashboard | KPI + hot_events + map_events | event_registry |
| GET /api/v1/events | 分页列表 + 筛选 (topic/country/impact) | event_registry |
| GET /api/v1/events/{event_id} | 完整 Event Dossier (解析JSON字段) | event_registry |
| GET /api/v1/sources | 来源注册表 + event_count | source_registry + 聚合 |
| GET /api/v1/search?q= | 全文搜索 | event_registry LIKE title/summary |
| GET /api/v1/map/events | 地图标记点 (country非空, 去重) | event_registry |

**验收**:
```bash
curl http://localhost:8000/api/v1/dashboard
# -> {"metrics": {"active_events": 9, ...}, "hot_events": [...], "map_events": [...]}

curl http://localhost:8000/api/v1/events/EVT-20260710-006
# -> {"event_id": "EVT-20260710-006", "facts": {"subject": "Apple", "action": "SUES", ...}, 
#     "timeline": [...], "source_chain": [...], "evidence": [...], "llm_analysis": {...}}

curl http://localhost:8000/api/v1/map/events
# -> {"events": [{"event_id": "...", "country": "Iran", "title": "...", ...}]}
```

**详细步骤**:
1. 创建 `backend/db.py`: 直连 event_registry SQLite (只读模式, `file:...?mode=ro`)
2. 创建 `backend/models/schemas.py`: Pydantic models 映射 frozen API Contract
   - EventDossier, DashboardResponse, EventListItem, SourceEntity, MapEvent
3. 创建 `backend/api/dashboard.py`:
   - metrics: COUNT WHERE stage IN ('active','developing','breaking')
   - hot_events: ORDER BY confidence DESC LIMIT 6
   - map_events: SELECT DISTINCT event_id, title, country WHERE country IS NOT NULL
4. 创建 `backend/api/events.py`:
   - list: SELECT + pagination (?page=&limit=&event_type=&location_country=)
   - detail: SELECT + json.loads(evidence, source_chain, timeline, actors, keywords, related_entities, llm_analysis)
5. 创建 `backend/api/sources.py`: SELECT source_registry + COUNT(event_registry.primary_source_id) GROUP BY
6. 创建 `backend/api/search.py`: WHERE title LIKE %q% OR summary LIKE %q%
7. 创建 `backend/api/map.py`: SELECT event_id, title, location_country, event_type, confidence WHERE location_country IS NOT NULL
8. 添加 CORS middleware (allow_origins=["http://localhost:3000"])
9. ~~添加 ingest endpoint~~ (V1 删除: 不做 PostgreSQL 写模型)

---

### Task-004: Dashboard 页面 + Global Event Map

**输入**: Task-002 + Task-003 完成
**输出**: Dashboard 页面显示真实事件数据 + 全球事件地图

```
┌──────────────────────────────────────────┐
│ ACTIVE EVENTS    CRITICAL    TODAY    SOURCES  │
│    9              2           42        25     │
├─────────────────────┬────────────────────┤
│  Global Event Map   │  Event Stream       │
│   [世界地图+标记]    │  ● Iran talks 5m    │
│                     │  ● Apple sues 1h    │
│                     │  ● Russia attack 2h │
├─────────────────────┴────────────────────┤
│  [Event Card] [Event Card] [Event Card]    │
│  [Event Card] [Event Card] [Event Card]    │
└──────────────────────────────────────────┘
```

**验收**:
- 4个 MetricCard 显示实际数字 (从 /api/v1/dashboard 获取)
- GlobalEventMap 显示标记点 (至少显示 country 非空的5+事件)
- 点击地图标记 → 跳转 /events/{id}
- EventGrid 显示 6 个 EventCard (真实数据)
- EventCard Hover: translateY(-2px) + shadow
- Critical 事件卡片左侧有 4px 红色竖线

**详细步骤**:
1. 创建 `lib/api.ts`: fetch wrapper (base URL, error handling)
2. 创建 `lib/types.ts`: TypeScript types 从 contracts/ 导入
3. 创建 `dashboard/MetricCard.tsx`: 120px高, 标题12px uppercase muted, 数字32px bold
4. 创建 `dashboard/GlobalEventMap.tsx`:
   - 使用 react-simple-maps (轻量, 无 API key 依赖)
   - 圆形标记: 位置用 country→coordinates 映射表
   - 标记颜色: Critical=红, High=橙, Medium=黄
   - 标记大小: radius = 4 + confidence * 8
   - Hover: tooltip 显示 title
   - Click: router.push(/events/{id})
5. 创建 `event/EventCard.tsx`: 320x180px, bg-card #151B26, border #263244
   - 左上 StatusDot (红/橙/黄/绿)
   - 标题 16px semi-bold
   - 底部 sources + update time
   - Hover: translateY(-2px), shadow-xl
   - Critical: border-l-4 border-red-500
6. 创建 `dashboard/EventGrid.tsx`: grid grid-cols-3 gap-4
7. 创建 `dashboard/EventStream.tsx`: 右侧实时时间线
8. `app/page.tsx`: fetch /api/v1/dashboard → 渲染 MetricCard + Map + Stream + EventGrid
9. 添加 Loading skeleton / Empty state / Error state

---

### Task-005: Event Dossier Detail ⭐⭐⭐ (核心验收)

**输入**: Task-002 + Task-003 完成
**输出**: /events/{id} 完整事件档案页 — 验证"信息→事件→情报展示"闭环

情报分析顺序：**事实 > 证据 > 传播 > 判断**

```
┌──────────────────────────────────────┐
│            Event Header               │
│  TITLE | ACTIVE | HIGH | ████░ 91%   │
├──────────────────────────────────────┤
│  Facts Panel                          │
│  Subject: 🇺🇸 US   Action: NEGOTIATE  │
│  Object: Iran     Location: MidEast   │
├──────────────────────────────────────┤
│           Timeline                    │
│  ● Jul 10 Initial report              │
│  │ Jul 11 Official response           │
│  ● Jul 12 Market reaction             │
├──────────────────────────────────────┤
│           Evidence                    │
│  "Officials confirmed..." — Reuters   │
│  "Markets reacted sharply..." — BBG   │
├──────────────────────────────────────┤
│           Source Chain                │
│  [Gov] → [Reuters PRIMARY] → [BBG]    │
├──────────────────────────────────────┤
│        AI Intelligence                │
│  Summary / Impact / Risk / Forecast   │
└──────────────────────────────────────┘
```

**验收**:
- EventHeader: 标题 + Stage Badge + Impact Badge + Confidence 进度条
- FactPanel: Subject/Action/Object/Location/Time 5行
- Timeline: 垂直时间线, 节点● + 竖线│ + 描述
- SourceChain: 流图 Gov → Reuters (PRIMARY) → Bloomberg (FOLLOW)
- EvidenceCard: 引用 + 来源 + "View Source →" 链接
- IntelligencePanel: bg=#172554, 摘要 + 市场信号 + 风险等级

**详细步骤**:
1. 创建 `event/EventHeader.tsx`: 200px高
   - title 24px bold
   - StatusDot + Stage Badge + Impact Badge 水平排列
   - Confidence bar: bg-gray-800 + fill-blue-500 (width=confidence%)
2. 创建 `event/FactPanel.tsx`: 5个 FactItem (120px height each)
   - 每行: 标签12px muted + 值14px primary
   - entity 类型加国旗emoji前缀 (Country → 🇺🇸, Company → 🏢, Person → 👤)
3. 创建 `event/Timeline.tsx`: 垂直布局
   - 每个节点: flex, 左侧 circle(8px) + line(1px #263244), 右侧 text
   - 最新节点 circle 蓝色 (#3B82F6)
4. 创建 `event/SourceChain.tsx`: 水平流图
   - Primary node: border-blue-500
   - Follow node: border-slate-500
   - 箭头连接
5. 创建 `event/EvidenceCard.tsx`: 卡片 bg-card
   - quote 14px italic
   - source + time 12px muted
   - "View Source →" 链接
6. 创建 `event/IntelligencePanel.tsx`: bg=#172554 rounded-xl
   - "AI INTELLIGENCE" 标题 + sparkle icon
   - Summary / Market Impact / Risk / Forecast 分区
7. `app/events/[id]/page.tsx`: fetch /api/v1/events/{id} → 渲染全部子组件
8. 添加 Loading: 骨架屏 (每个 section 的 placeholder)
9. 添加 Error: "Event not found" if 404

---

### Task-006: Event Explorer 页面

**输入**: Task-002 + Task-003 完成
**输出**: /events 表格页面 with 筛选

```
┌──────────────────────────────────────────┐
│ Filters: [Topic ▼] [Country ▼] [Impact ▼]  │
├──────────────────────────────────────────┤
│ Event              | Topic    | Impact | ... │
│ Iran Nuclear Talks | Diplo    | HIGH   | 5m │
│ Apple Sues OpenAI  | Legal    | MEDIUM | 1h │
│ ...                                        │
├──────────────────────────────────────────┤
│            ← 1 2 3 ... 10 →               │
└──────────────────────────────────────────┘
```

**验收**:
- 表格显示真实事件数据 (从 /api/v1/events 获取)
- 列: Event(40%), Topic(15%), Impact(10%), Sources(10%), Updated(15%)
- 筛选器: Topic下拉 / Country下拉 / Impact下拉
- 分页: 上一页 / 页码 / 下一页
- 点击行 → 跳转 /events/{id}
- Hover: bg-#1E293B, cursor-pointer

**详细步骤**:
1. 创建 `common/Table.tsx`: 通用表格组件
   - Header: bg-#111827, height 44px
   - Row: height 64px, Hover bg-#1E293B
2. 创建筛选器: useSearchParams 管理 query params
   - Topic dropdown: Military/Diplomatic/Economic/Legal/...
   - Country dropdown: 从 distinct countries 动态填充
   - Impact dropdown: HIGH/MEDIUM/LOW
3. `app/events/page.tsx`:
   - fetch /api/v1/events?page=1&topic=X&country=Y
   - 渲染 Table + Pagination
   - onClick → router.push(/events/{event_id})
4. Pagination: 显示总页数, 当前页高亮
5. 添加 Loading: 表格行 skeleton
6. 添加 Empty: "No events match filters" + clear filters button

---

### Task-007: Sources + Search 页面

**输入**: Task-002 + Task-003 完成
**输出**: Sources 卡片网格 + Search 搜索页面

**验收**:
- Sources: 卡片网格, 每张显示 name, authority, event_count, type badge
- Search: 600x48 搜索框, 实时搜索结果列表 (EventCard 形式)
- 两个页面均加载真实数据

**详细步骤**:
1. `app/sources/page.tsx`: fetch /api/v1/sources
   - 卡片网格: grid grid-cols-3
   - 每张: name 14px bold, authority 数字, event_count, type Badge
   - Hover 效果同 EventCard
2. `app/search/page.tsx`:
   - SearchBox 600x48, focus: border-blue-500
   - useDebounce(300ms) 防抖
   - fetch /api/v1/search?q=...
   - 结果列表: EventCard 组件复用
3. 添加 Loading + Empty state

---

### Task-008: UI Polish + QA

**输入**: Task-001~007 全部完成
**输出**: 生产就绪的 Web V1

**验收标准（冻结）**:
1. 打开 Dashboard → 看到 KPI + 全球地图 + Event Card (真实数据)
2. 点击 Event Card → 进入 Event Detail → 看到 Facts → Timeline → Evidence → SourceChain → AI Intelligence
3. 从 Explorer 筛选 "Military" + "HIGH" → 显示匹配事件
4. 搜索 "Iran" → 返回相关事件
5. Sources 页面 → 显示所有来源卡片
6. Loading/Empty/Error/Mobile fallback 全部覆盖
7. 页面间导航 < 200ms (client-side routing)
8. Dark Theme 风格统一, 无样式闪动
9. 地图标记可点击 → 跳转事件详情

**详细步骤**:
1. 全局 Loading skeleton 组件 (SkeletonCard, SkeletonTable, SkeletonDetail)
2. 全局 Error boundary: "Something went wrong" + retry + error detail
3. 全局 Empty state: 插图 + 说明文字 (每个页面定制)
4. Mobile fallback: min-width 1024px, 低于此宽度显示 "请使用桌面浏览器" 提示
5. 添加页面过渡动画 (framer-motion fadeIn)
6. 确认所有颜色使用 CSS 变量 (非硬编码)
7. `npm run build` 无 error 和 warning
8. 最终验收: 按上述 9 条标准逐项通过

---

## 每个 Task 的通用验收格式

```
[ ] 代码编译无 error (npm run build / python -c "import main")
[ ] 页面渲染真实数据 (从 event_registry 读取, 非 mock)
[ ] Loading 状态可见 (Skeleton 组件)
[ ] Empty 状态有效 (0条数据时, 每页面定制)
[ ] Error 状态有效 (API 不可用时, 含 retry)
[ ] Hover 效果符合设计规范
[ ] Dark Theme 颜色全部使用 CSS 变量 (非硬编码)
```

## 文件清单

| 层 | 文件 | 用途 |
|----|------|------|
| Contract | `frontend/src/contracts/event.ts` | TypeScript 接口 (冻结) |
| Contract | `frontend/src/contracts/dashboard.ts` | Dashboard 响应类型 |
| Contract | `frontend/src/contracts/source.ts` | Source 实体类型 |
| Backend | `backend/main.py` | FastAPI 入口 |
| Backend | `backend/db.py` | SQLite 只读连接 |
| Backend | `backend/models/schemas.py` | Pydantic models |
| Backend | `backend/api/dashboard.py` | GET /api/v1/dashboard |
| Backend | `backend/api/events.py` | GET /api/v1/events, /events/{id} |
| Backend | `backend/api/sources.py` | GET /api/v1/sources |
| Backend | `backend/api/search.py` | GET /api/v1/search |
| Backend | `backend/api/map.py` | GET /api/v1/map/events |
| Frontend | `frontend/src/app/page.tsx` | Dashboard 页面 |
| Frontend | `frontend/src/app/events/page.tsx` | Explorer 页面 |
| Frontend | `frontend/src/app/events/[id]/page.tsx` | Detail 页面 |
| Frontend | `frontend/src/app/sources/page.tsx` | Sources 页面 |
| Frontend | `frontend/src/app/search/page.tsx` | Search 页面 |

---

**数据就绪**: ✅ event_registry 10/10 关键字段已验证
**依赖**: 无阻塞依赖。现有 pipeline + SQLite 可直读
**总预计工时**: 8个 Task，按顺序执行
