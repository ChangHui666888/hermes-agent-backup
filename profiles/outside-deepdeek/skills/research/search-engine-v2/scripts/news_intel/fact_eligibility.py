"""fact_eligibility.py — Event Relevance Filter (P0, ISS-20260810-012)

把"文章是否应产 Fact"从"Fact 抽取精度"剥离:
  Article → EVENT / NON_EVENT / UNCERTAIN
    NON_EVENT → facts=[] (市场综述/分析/评论/解读/说明文/观点)
    EVENT     → 进入 Fact Extraction
    UNCERTAIN → 灰区, 默认按 EVENT 处理(P0 不叠 Qwen 过滤器)

第一版 Rule-based(标题/来源/动作/文章类型关键词), 分层低成本; 灰区才允许交 AI(后续)。
契约: references/fact-schema-v2.md §6 Gate 2
"""
import re

# 明确 NON_EVENT 标题 (综述/分析/解读/说明/观点)
_NON_EVENT_TITLE = [
    r"what does it take", r"latest .* news", r"news and analysis", r"weekly (review|recap|roundup)",
    r"monthly (review|recap)", r"market (news|recap|roundup|preview|wrap)", r"outlook",
    r"the case for", r"why .* matters", r"explainer", r"faq", r"recap", r"roundup", r"preview",
    r"analyst (corner|commentary|note)", r"opinion", r"op-?ed",
    r"commentary", r"editorial", r"perspective", r"what to expect", r"^how ", r"^is .* worth",
    r"the real challenger", r"story in", r" vs\.? ", r"won'?t be", r"isn'?t", r"peak oil",
    r"contending with", r"the (unaccountability|forgotten|wealthy) ",
]
# 明确 EVENT 动作 (标题/正文命中 → EVENT)
_EVENT_ACTION = [
    r"announc", r"acquir", r"launch", r"sanction", r"attack", r"strike", r"reject", r"vote",
    r"warn", r"raise", r"cut", r"sign", r"agree", r"hit", r"execut", r"deploy", r"invad",
    r"withdraw", r"seize", r"arrest", r"indict", r"\bban", r"approve", r"confirm", r"hack",
    r"reopen", r"\bclose", r"halt", r"suspend", r"invest", r"merge", r"\bipo", r"\blist",
    r"rejects?", r"denies?", r"condemn", r"sanction", r"execut", r"kills?", r"drill", r"test",
]
# 分析/评论暗示 (兜底 → NON_EVENT)
_NON_EVENT_HINT = [
    r"\banalyst", r"\banalysis", r"\bcommentary", r"\bopinion", r"\breview", r"\boutlook",
    r"\bforecast", r"\bperspective", r"\beditorial", r"\bcolumn",
]
# 中文: 明确 EVENT 动作 (报道事实, 防分析词误杀) — P1 最小修复 (ISS-20260810-012)
_EVENT_ACTION_ZH = [
    r"宣布", r"拒绝", r"制裁", r"攻击", r"袭击", r"轰炸", r"征收", r"出口管制", r"签署", r"同意",
    r"访问", r"会晤", r"警告", r"起诉", r"逮捕", r"发射", r"收购", r"合并", r"上市", r"任命",
    r"解雇", r"撤出", r"部署", r"增兵", r"通过.{0,6}(法案|决议|立法|审查|批准)", r"批准", r"否认", r"定于", r"将(对|向|在).*(征|禁|制裁|推|发布)",
]
# 中文: 分析/综述/观点 标题 (标题以分析词结尾 或 修辞"如何/为何…?" 或 媒体评论) — P1 最小修复
_NON_EVENT_TITLE_ZH = [
    r".*(分析|综述|解读|评论|观点|观察|展望|预测|研判|盘点|回顾|复盘|专题|深度|详解|解析|评析|调查|报告|周刊|前瞻|启示|思考)$",
    r"^(深度解读|深度分析|专家观点|市场观察|特稿|专题|锐评|快评|盘点|回顾|复盘|深度|详解|解析|评析|调查|报告|前瞻|分析|综述|解读|评论|观点|观察|展望|预测|研判)[:：]",
    r"(如何|为何|能否|是否|如何看待|何方|何去何从)",  # 修辞性标题 → 分析 (如 "中国如何…?" "走向何方?")
    r"(德语媒体|外媒|媒体|专栏|评论|观点|编者按).*(分析|解读|看法|观点|担忧|影响|认为)",
]
# 中文: 正文开头分析框架 (如 "全球关注…能否…之际") + 媒体分析 (如 "《新苏黎世报》分析称")
_NON_EVENT_DESC_ZH = (r"^(全球|外界|市场|专家|业内|各方|美媒|德媒|分析人士).*(能否|是否|之际|而言|来看|认为|动向|展望)"
                      r"|(《[^》]*》|德语媒体|外媒).*(分析|解读|评论|观点|认为)")


def _is_zh_analysis(title: str, desc: str) -> bool:
    return (any(re.search(p, title) for p in _NON_EVENT_TITLE_ZH)
            or bool(re.search(_NON_EVENT_DESC_ZH, (desc or "")[:100])))


def _is_cjk(t):
    return any('一' <= c <= '鿿' for c in (t or ""))


def classify(article: dict) -> str:
    """返回 EVENT / NON_EVENT / UNCERTAIN。"""
    title = article.get("title") or ""
    desc = article.get("description") or ""
    title_l = title.lower()
    text = (title + " " + desc[:200]).lower()
    cjk = _is_cjk(title + " " + desc[:80])
    # 英文 NON_EVENT 标题优先
    if any(re.search(p, title_l) for p in _NON_EVENT_TITLE):
        return "NON_EVENT"
    # 中文: 明确 EVENT 动作 → 报道事实 (优先于分析词)
    if cjk and any(re.search(p, text) for p in _EVENT_ACTION_ZH):
        return "EVENT"
    # 中文: 分析意图 (标题/正文开头) → NON_EVENT
    if cjk and _is_zh_analysis(title, desc):
        return "NON_EVENT"
    # 明确 EVENT 动作 (英文)
    if any(re.search(p, text) for p in _EVENT_ACTION):
        return "EVENT"
    # 分析/评论暗示 (英文兜底)
    if any(re.search(p, text) for p in _NON_EVENT_HINT):
        return "NON_EVENT"
    return "UNCERTAIN"


def is_event(article: dict) -> bool:
    """P0 门: NON_EVENT → 不产 Fact; EVENT/UNCERTAIN → 产 Fact。"""
    return classify(article) != "NON_EVENT"
