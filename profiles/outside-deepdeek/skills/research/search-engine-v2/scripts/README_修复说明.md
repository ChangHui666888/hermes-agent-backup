# news_intel Pipeline 修复包

对应问题：`CHECK FETCHER: FAIL` + RSS(19543) 与 Pipeline(3949) 数量不一致。

所有修改都已经过语法检查（`py_compile`）和逻辑验证（见文末"我做过的测试"），
可以直接替换你项目里的同名文件。**建议部署前先备份 `news_intel.db`。**

## 改了哪些文件

```
news-pipeline.py              加 --fetch/--no-fetch 开关(默认True并透传do_fetch)；修复日志摘要字段名
news-pipeline.sh              同步修复内嵌摘要脚本的字段名
news_intel/pipeline.py        Tier过滤 'A' → 'A','B'
news_intel/pipeline_check.py  fetcher阶段命令路径修正
news_intel/sync.py            引入持久化游标(watermark)，替代纯"最近N小时"滑动窗口
news_intel/db.py              新增 sync_state 表 + 游标读写函数
verify_fix.py                 【新增】只读校验脚本，不改数据
```

## 部署步骤

1. 备份现有 `news_intel.db`（务必做，游标机制会新建一张表，虽然是 `IF NOT EXISTS`，但求稳）。
2. 用本包里的文件覆盖你项目里的同名文件（路径结构一致，直接覆盖即可）：
   - `search-engine-v2/scripts/news-pipeline.py`
   - `search-engine-v2/scripts/news-pipeline.sh`
   - `search-engine-v2/scripts/news_intel/pipeline.py`
   - `search-engine-v2/scripts/news_intel/pipeline_check.py`
   - `search-engine-v2/scripts/news_intel/sync.py`
   - `search-engine-v2/scripts/news_intel/db.py`
3. 手动跑一次，观察输出（不要等 cron，先手动确认）：
   ```
   python news-pipeline.py --hours 2 --limit 50
   ```
   预期日志里能看到 `[fetch] 抓取 N 篇全文...`，摘要里 `Enhanced`、`Tier A/B` 数字不再是 0。
4. （可选，如果想追平 RSS 历史积压）在 `news_intel/` 目录下跑一次性回填：
   ```
   python -m news_intel.sync --catchup --limit 500
   ```
   这会自动分批把从上次游标（或首次运行的兜底窗口）到现在的所有积压追平，
   直到没有更多新数据为止，不会因为单批 LIMIT 而丢数据。
5. 用 `verify_fix.py` 校验（部署前后都可以跑，对比数字变化）：
   ```
   python verify_fix.py --db "C:\Users\ChangHui\AppData\Local\hermes\profiles\outside-deepdeek\skills\research\search-engine-v2\scripts\news_intel\news_intel.db"
   ```
6. 观察几天后，用 `python pipeline_check.py check` 走完整检查链，`FETCHER` 应该从 FAIL 变 PASS（`missing=0` 或 `missing` 持续下降），`rss_raw` 总量增速应该逐渐追上 RSS 源的 `latest24h`。

## 每个改动具体是什么、为什么这么改

### 1. `news-pipeline.py` — 补上 `--fetch` 并默认开启

**问题**：cron 实际调用的入口从来没把 `--fetch` 传给 `run_pipeline()`，`do_fetch` 永远是默认值 `False`，`batch.py` 从未被真正调用过。

```python
# 新增
parser.add_argument("--fetch", dest="fetch", action="store_true", default=True,
                     help="抓取正文（默认开启）")
parser.add_argument("--no-fetch", dest="fetch", action="store_false",
                     help="跳过正文抓取，仅评分")
...
report = run_pipeline(hours=args.hours, limit=args.limit, do_fetch=args.fetch) or {}
```

默认 `True`，所以哪怕你 Windows 计划任务里的命令行没改，抓取也会自动生效；如果只想快速看评分结果不想抓正文，显式加 `--no-fetch`。

同时修了 `print_summary()`：原来读的是 `processed/tier_a/duplicate/enhanced/saved/failed` 这些 key，但 `run_pipeline()` 实际返回的是 `batch_input/batch_tier_a/batch_duplicate/batch_enhanced/total_articles` 这些 key，两边完全对不上，导致 cron 日志摘要一直显示 0，长期掩盖了"抓取从未跑过"这件事。现在摘要读的是真实字段名。

`news-pipeline.sh` 里内嵌的那段 python 摘要打印脚本有同样的字段名 bug，一并修了。

### 2. `news_intel/pipeline.py` 第66行 — Tier 过滤条件

```python
# 修复前
WHERE ni.tier IN ('A')
# 修复后
WHERE ni.tier IN ('A', 'B')
```

注释、下游的 `tier_counts` 统计、打印信息里都在说"处理 Tier A/B"，唯独这行 SQL 只写了 `'A'`。用你上传的真实 `news_intel.db` 验证过：修复前候选池是 0（Tier A 的4篇早就有 content 了，没有新的可抓），修复后候选池变成 367（Tier B 里所有还没抓的文章）。

### 3. `news_intel/pipeline_check.py` — fetcher 阶段命令路径

```python
# 修复前: SEARCH_ENGINE_HOME / "news_intel" / "batch.py"   ← 不存在
# 修复后: SEARCH_ENGINE_HOME / "batch.py"                   ← 实际位置
```

不修的话，`python pipeline_check.py fetcher`（用来单独手动补跑/验证抓取阶段）会直接因为文件不存在而失败。

### 4. `news_intel/sync.py` + `news_intel/db.py` — 持久化同步游标

**问题**：旧版每次只看"当前时间往前推 N 小时"的滑动窗口 + 硬 LIMIT。cron 一旦漏跑，落在窗口外的 RSS 文章永久丢失，没有任何补偿机制。

**修复**：`db.py` 新增 `sync_state` 表记录游标（`rss_last_synced_at`）；`sync.py` 改成"从游标往后拉，处理完把游标推进到本批次最大的 `created_at`"。只有从未同步过（游标为空）时才退回到"最近N小时"兜底。新增 `sync_catchup()` / `--catchup`，可以自动分批追平任意长度的积压，不受单批 LIMIT 限制。

## 我做过的测试

1. **语法检查**：所有改动文件 `python3 -m py_compile` 全部通过。
2. **游标机制 vs 旧滑动窗口 对比模拟**：构造了一个"cron 中断6小时"的模拟场景（10小时、共500篇模拟RSS文章），
   - 旧逻辑（滑动窗口）：只捕获 249/500 篇，丢失 251 篇（50%）
   - 新逻辑（持久化游标）：捕获 499/500 篇，仅丢失 1 篇（首次冷启动窗口边界的正常誤差）
3. **端到端集成测试**（真实 `sync.py`/`db.py` 代码路径，非简化模拟）：
   - 连续跑 3 次 `sync_recent()`，验证游标正确写入 `sync_state` 并让重复调用不再重复处理
   - 跑 `sync_all()`，验证 500 篇历史积压能自动分 5 批（120+120+120+120+20）追平，无丢失
4. **Tier 过滤修复效果**：直接在你上传的真实 `news_intel.db` 上跑新旧两条 SQL 对比，候选池从 0 → 367。
5. **参数解析验证**：确认 `--fetch`/`--no-fetch`/默认值 三种情况下 `do_fetch` 结果符合预期。

没有做的：没有实际跑 `batch.py` 抓真实网页（这边网络环境访问不了 Reuters/Bloomberg 这些站点），所以 `core/fetchers.py` 里各策略（direct/archive/scrapling）在你 Windows 机器上的真实抓取成功率，需要你部署后用少量样本手动验证一下——目前样本量太小（历史上只成功过5次），还不能排除域名级别的技术性抓取问题（反爬/超时/证书等）。如果部署后发现 `content_ok` 依然很低但 `content_total`（候选池处理数）已经正常增长，那就是 `core/fetchers.py` 层面的问题了，需要再单独排查。
