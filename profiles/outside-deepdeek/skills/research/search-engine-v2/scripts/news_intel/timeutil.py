"""北京时间时区工具 (2026-08-15)。

全链路业务时间统一为 naive 北京时间 (Asia/Shanghai, UTC+8):
- scanner `_parse_date` 把源原始时区日期转北京时间 naive
- aggregator/scorer/event_normalizer 用 `beijing_now()` 生成"现在"
- 输出一律 naive (无 tzinfo), 与存量 naive 语义一致, 避免 aware/naive 混算 TypeError
"""
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    BEIJING_TZ = ZoneInfo("Asia/Shanghai")
except Exception:  # 无 tzdata 时回落固定偏移
    from datetime import timezone, timedelta
    BEIJING_TZ = timezone(timedelta(hours=8))


def beijing_now() -> datetime:
    """当前北京时间, 返回 naive (无 tzinfo)。"""
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)


def to_beijing_naive(dt):
    """任意 datetime → naive 北京时间。

    aware → astimezone(北京) 后剥 tzinfo; naive → 视为已是北京时间原样返回。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(BEIJING_TZ).replace(tzinfo=None)


def beijing_now_iso() -> str:
    """当前北京时间 ISO (带微秒, 与 aggregator 的 .isoformat() 输出格式一致)。"""
    return beijing_now().isoformat()
