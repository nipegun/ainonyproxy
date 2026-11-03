#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Date helpers. The native format of the application is the storage format:

  Storage (always UTC):  2026-10-29@13-59-59.723
  Display (always UTC):  2026/10/29@13:59:59.723

Any other format must be calculated from the native one with a function of
this module, never written by hand somewhere else.
"""

from datetime import datetime, timedelta, timezone


cStorageDateFormat = "%Y-%m-%d@%H-%M-%S"
cDisplayDateFormat = "%Y/%m/%d@%H:%M:%S"

# Same storage format, produced by SQLite itself (%f is "SS.SSS")
cSqliteStorageNow = "strftime('%Y-%m-%d@%H-%M-%f', 'now')"


def fDatetimeToStorage(pDatetime: datetime) -> str:
  """Converts a datetime into the storage format, in UTC"""
  if pDatetime.tzinfo is None:
    pDatetime = pDatetime.replace(tzinfo=timezone.utc)
  vUtc = pDatetime.astimezone(timezone.utc)
  return f"{vUtc.strftime(cStorageDateFormat)}.{vUtc.microsecond // 1000:03d}"


def fNowStorage() -> str:
  """Returns the current moment in the storage format"""
  return fDatetimeToStorage(datetime.now(timezone.utc))


def fStorageAgo(pDays: float = 0, pHours: float = 0) -> str:
  """Returns, in the storage format, the moment that was pDays and pHours ago"""
  return fDatetimeToStorage(datetime.now(timezone.utc) - timedelta(days=pDays, hours=pHours))


def fStorageFromNow(pDays: float = 0, pHours: float = 0) -> str:
  """Returns, in the storage format, the moment pDays and pHours from now"""
  return fDatetimeToStorage(datetime.now(timezone.utc) + timedelta(days=pDays, hours=pHours))


def fStorageToDatetime(pText: str) -> datetime:
  """Converts a date in the storage format into a UTC datetime"""
  try:
    vSeconds, vMilliseconds = pText.split(".", 1)
    vDatetime = datetime.strptime(vSeconds, cStorageDateFormat)
    return vDatetime.replace(microsecond=int(vMilliseconds[:3].ljust(3, "0")) * 1000, tzinfo=timezone.utc)
  except (ValueError, AttributeError) as vError:
    raise ValueError(f"Not a date in the storage format: {pText!r}") from vError


def fStorageToDisplay(pText: str) -> str:
  """Converts a date in the storage format into the display format"""
  try:
    vDatetime = fStorageToDatetime(pText)
    return f"{vDatetime.strftime(cDisplayDateFormat)}.{vDatetime.microsecond // 1000:03d}"
  except ValueError:
    return pText or ""
