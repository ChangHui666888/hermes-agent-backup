# V4.3 聚合器升级要点

## P0 修复

1. **Action 计数排序**: `_detect_action` 从"字典顺序首次命中"改为"计数排序取最高分"
   - 修复: `CEASEFIRE`/`NEGOTIATES` 不再被 `ATTACKS` 抢走
   - 位置: `aggregator.py:117-130`

2. **Tehran 重复 key**: `ENTITY_CANONICAL` 中 `"Tehran":"Iran"` 被 `"Tehran":"Iranian Government"` 静默覆盖
   - 修复: 删除重复, Tehran 仅映射到 Iran
   - 影响: 不同country精确比较拒绝合并的隐藏bug

3. **test_aggregator IDF**: 诊断工具未传 `global_idf`/`topic_idf_map` → 显示的指纹与真实聚类不一致
   - 修复: 预计算 IDF, 全程复用传参

## P1 修复

4. **DIES 正则补全**: `assassinat(?:ed?|es?|ion)|killing|mourning` → 修复 Khamenei 死亡新闻误判 ATTACKS

5. **Hub dampening + MIN_SUBJECT_WEIGHT**:
   - `HUB_RATIO=0.15, freq>=5` → 高频实体降权70%但不禁用
   - `MIN_SUBJECT_WEIGHT=0.15` → 低于此阈值的实体不选为 subject

## P2 修复

6. **稀有度加权打分**: subject_weight/object_weight 存入 fingerprint, `fingerprint_score` 按 `10 + 15 × min(rarity/0.4, 1.0)` 动态给分

7. **Coherence 一致性**: 事件输出增加 `coherence` 字段 (簇内 pairwise 指纹得分均值)
   - 低一致性簇 (coherence < 75) 禁止评 HIGH

8. **Frozen Schema**: 21字段标准化事件输出

## 测试结果 (100篇)

```
Apple-OpenAI: 8篇, coherence=95.7, confidence=0.89 ✅
Iran 事件: 从1个超大簇拆为4个独立事件 ✅
CEASEFIRE/NEGOTIATES 正确识别 ✅
DIES 正确分类 Khamenei 相关文章 ✅
```
