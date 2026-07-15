# Open Source Intelligence Projects — 借鉴评估报告

## 当前 V8 架构对照

```
已有:
  ✅ Event Registry (71 events, SAO model — 类 GDELT CAMEO)
  ✅ Source Chain (break/follow — 类 Liveuamap 来源追踪)
  ✅ Timeline (按小时聚合)
  ✅ Evidence (引用原文)
  ✅ Dashboard (态势感知 — 类 World Monitor)
  ✅ World Map (react-simple-maps)
  ✅ 12-page Next.js 前端

缺失:
  ❌ 3D Globe (Cesium)
  ❌ Entity Relationship Graph (OpenCTI)
  ❌ 大规模热力图 (Kepler.gl)
  ❌ 地理核验 (GeoConfirmed)
  ❌ 多源融合 (卫星/AIS/航班)
```

## 逐项评估

### 1. GDELT — 事件模型参考

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐⭐⭐ |
| 当前差距 | SAO 模型已接近 GDELT CAMEO，但缺少 Tone/Goldstein 情绪评分 |
| 建议 | **V1 不动**，V2 增加 Tone 字段到 Event Dossier |
| 风险 | GDELT 数据量大(每15min全球)，我们的 41 事件粒度不够 |

### 2. Liveuamap — 产品结构

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐⭐ |
| 当前差距 | 缺少 Event 列表 + Map 联动视图 |
| 建议 | Geo Monitor 页面改为左侧事件列表 + 右侧地图联动 |
| 风险 | 我们只有 8 marker，Liveuamap 有数百个；数据量不足时地图显空 |

### 3. World Monitor — Dashboard

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐ |
| 当前差距 | 缺少多源数据图层(船舶/航班/天气) |
| 建议 | **V1 不做**，那是 GIS 平台不是情报平台 |
| 风险 | 功能蔓延，背离"事件情报"核心定位 |

### 4. OpenCTI — 实体知识图谱

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐⭐⭐ |
| 当前差距 | 无实体关系图, 无 STIX2 格式 |
| 建议 | **V2** 引入 entity_registry 的图可视化 |
| 风险 | 图数据库(Neo4j)运维复杂度，V2 先用 D3.js 内存图 |

### 5. Cesium — 3D Globe

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐ |
| 当前差距 | react-simple-maps 是 2D |
| 建议 | **V1 不做**，3D 对新闻事件展示增益极小 |
| 风险 | 性能开销大，3.9GB 云主机无法承载 |

### 6. Kepler.gl — 大规模热力图

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐ |
| 当前差距 | 无热力图 |
| 建议 | **V1 不做**，71 events 不需要百万级可视化 |
| 风险 | 过度工程化 |

### 7. GeoConfirmed — 证据核验

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐⭐ |
| 当前差距 | Evidence 仅引用原文，无地理/图片验证 |
| 建议 | **V3** 增加 evidence.verification_level 字段 |
| 风险 | 需要图片/视频分析能力，需 LLM 辅助 |

### 8. MapLibre — 地图底座

| 维度 | 评估 |
|------|------|
| 借鉴价值 | ⭐⭐⭐⭐⭐ |
| 当前差距 | react-simple-maps 功能有限 |
| 建议 | **V2** 替换为 MapLibre GL JS，支持自定义图层和样式 |
| 风险 | 需自建 tile server 或用免费 CDN |

## 最终建议

### V1 (当前) — 不动

```
不引入任何新依赖。专注稳定性和数据覆盖。
```

### V2 (下阶段) — 3 个改进

| 优先级 | 改进 | 来源参考 |
|:--:|------|------|
| 1 | MapLibre 替换 react-simple-maps | MapLibre |
| 2 | Event 列表 + Map 联动 | Liveuamap |
| 3 | Entity 关系图 (D3.js 内存图) | OpenCTI |

### V3 (远期) — 2 个改进

| 优先级 | 改进 | 来源参考 |
|:--:|------|------|
| 1 | Event Tone/Goldstein 评分 | GDELT |
| 2 | Evidence 验证级别 | GeoConfirmed |

### 不推荐引入

| 项目 | 原因 |
|------|------|
| Cesium 3D Globe | 性能开销、定位偏离 |
| Kepler.gl | 数据量不足 |
| World Monitor 多源图层 | 非情报平台方向 |
| MISP 情报共享 | 需要多用户体系 |
| OSINT Mapping Tool | 手动输入，非实时 |
