# V2/V3 落地评估 — 补充建议审视报告

## 一、补充建议逐项判决

### 1. MapLibre 底图成本 — CartoDB Dark Matter ✅ 合理

| 维度 | 评估 |
|------|------|
| 方案 | 免费 CDN 矢量瓦片，零自建成本 |
| 验证 | `https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json` |
| 风险 | 境外 CDN 可能被墙，需备选国内源 |
| 结论 | **V2 采用**，同时准备 Maptiler 免费计划作备选 |

### 2. LLM 合并提取 — ✅ 合理且必须

| 维度 | 评估 |
|------|------|
| 当前 | enhancers.py 已做一次调用输出 tags+entities+summary |
| 扩展 | 在现有 QMERGE_PROMPT 中加 `tone`/`relation_type` 字段 |
| 成本 | 0 额外 Token 消耗 |
| 结论 | **V2 直接扩展现有 Prompt，不发第二次调用** |

### 3. event_relations 表 — ✅ 合理，但需修正

当前 event_registry 已有 SAO 字段：

```sql
-- 已有字段，无需新建表
subject_name, subject_type,   -- 主体
action_type, action_detail,   -- 关系
object_name, object_type      -- 客体
```

SAO 本身就是关系三元组。新增 `event_relations` 表会造成冗余。正确做法：

```sql
-- V2: 在现有 events 表加字段（零冗余）
ALTER TABLE events ADD COLUMN tone FLOAT;           -- GDELT Tone (-10 ~ +10)
ALTER TABLE events ADD COLUMN goldstein FLOAT;      -- Goldstein 冲突/合作评分
```

事件间关系（因果/升级/包含）才需要单独表：

```sql
-- V2: 仅事件间因果关系需要新表
CREATE TABLE event_relations (
    id SERIAL PRIMARY KEY,
    parent_event_id VARCHAR(50) REFERENCES events(event_id),
    child_event_id VARCHAR(50) REFERENCES events(event_id),
    relation_type VARCHAR(20),  -- ESCALATION / DEESCALATION / CAUSAL / RELATED
    confidence FLOAT DEFAULT 1.0
);
```

| 原建议 | 问题 | 修正 |
|------|------|------|
| event_relations 含 subject/action/object | 与 events 表 SAO 字段重复 | SAO 留在 events 表，relation 表仅存事件间关系 |
| confidence 用 NUMERIC(3,2) | PG 规范：FLOAT 更通用 | 改为 FLOAT |

### 4. zustand 状态管理 — ⚠️ 部分合理

| 维度 | 评估 |
|------|------|
| 场景 | Event 列表悬停 → Map 联动 |
| 当前 | react-simple-maps 不支持 flyTo，MapLibre 才需要 |
| zustand | 对当前 V1 是过度引入（71 events 无性能问题） |
| 结论 | **V1 不需要**，V2 引入 MapLibre 时再评估是否需要 |

V2 替代方案：直接在 MapLibre 组件内用 `useRef` + DOM 事件，无需全局状态库。

### 5. CartoDB Dark Matter 样式 — ✅ 直接可用

实测 URL 可访问，Dark 主题与 Sentinel 颜色一致。

### 6. 报告关于 V2/V3 的技术路线 — ✅ 完全合理

| 建议 | 判决 |
|------|:--:|
| 不引入 Cesium/Kepler/World Monitor | ✅ 正确 |
| MapLibre 替代 react-simple-maps | ✅ V2 必做 |
| LLM 合并提取 | ✅ V2 扩展现有 Prompt |
| 零成本/零依赖原则 | ✅ 与 V8 开发理念一致 |

---

## 二、V2/V3 修正路线

### V2 (下一阶段)

```
优先级 1: MapLibre GL JS
  - 替换 react-simple-maps
  - 底图: CartoDB Dark Matter (CDN)
  - 备选: Maptiler 免费计划

优先级 2: Event 列表 + Map 联动
  - Geo Monitor 改造: 左侧事件卡片 + 右侧地图
  - hover 卡片 → map.flyTo()

优先级 3: GDELT Tone 评分
  - events 表加 tone/goldstein 列
  - enhancers.py Prompt 扩展 (零额外 LLM 调用)

优先级 4: Entity 关系可视化
  - event_relations 表 (仅事件间关系)
  - D3.js 力导向图 (内存, 无需图数据库)
```

### V3 (远期)

```
优先级 1: Evidence 验证级别
  - evidence 表加 verification_level 字段
  - GeoConfirmed 参考: confirmed/unconfirmed/disputed

优先级 2: STIX2 导出
  - 事件 Object 支持 STIX2 标准格式
  - 为未来 OpenCTI 集成预留接口
```

### 不引入清单 (维持原判)

```
❌ Cesium 3D Globe
❌ Kepler.gl
❌ World Monitor 多源图层
❌ MISP
❌ Neo4j 图数据库
❌ zustand (V1 不需要)
❌ 自建 Tile Server
```

---

## 三、与原 V8_TASK_PLAN.md 的衔接

V8 6 阶段完成后，新增 P7：

```
P7: V2 升级
  P7-1: MapLibre 替换 react-simple-maps (3h)
  P7-2: Geo Monitor Event-Map 联动 (2h)
  P7-3: Event tone/goldstein + Prompt 扩展 (1h)
  P7-4: event_relations 表 + D3.js 关系图 (3h)
  总计: 9h
```
