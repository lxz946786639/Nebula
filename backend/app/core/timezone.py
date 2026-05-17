from datetime import datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")


def now_china() -> datetime:
    return datetime.now(CHINA_TZ)


def as_china(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=CHINA_TZ)
    return value.astimezone(CHINA_TZ)
