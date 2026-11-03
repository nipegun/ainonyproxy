#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import os
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from config import fGetConfig
from services.dates import cSqliteStorageNow, fStorageAgo


@dataclass
class RequestRecord:
  id: Optional[int] = None
  timestamp: str = ""
  mode: str = "route"
  provider: str = ""
  model: str = ""
  pii_detected: bool = False
  entities: str = ""
  latency_ms: int = 0
  scan_time_ms: int = 0
  prompt_tokens: Optional[int] = None
  completion_tokens: Optional[int] = None
  user_agent: Optional[str] = None
  language: str = "en"
  language_fallback: bool = False
  detected_language: Optional[str] = None
  original_content: Optional[str] = None
  masked_content: Optional[str] = None
  provider_response: Optional[str] = None
  client_response: Optional[str] = None


@dataclass
class Statistics:
  total_requests: int = 0
  pii_requests: int = 0
  pii_percentage: float = 0.0
  upstream_requests: int = 0
  local_requests: int = 0
  avg_scan_time_ms: int = 0
  total_tokens: int = 0
  requests_last_hour: int = 0


def fOpenDatabase(pDbPath: str) -> sqlite3.Connection:
  """Opens the SQLite database, creating its folder readable only by its owner"""
  vDir = Path(pDbPath).parent
  try:
    if vDir:
      vDir.mkdir(parents=True, exist_ok=True, mode=0o700)
  except OSError as vError:
    print(f"Error creating the database folder: {vError}")
    raise

  vIsNew = not Path(pDbPath).exists()
  try:
    vDb = sqlite3.connect(pDbPath, check_same_thread=False, timeout=15)
    vDb.row_factory = sqlite3.Row
  except sqlite3.Error as vError:
    print(f"Error connecting to the database: {vError}")
    raise

  if vIsNew:
    try:
      os.chmod(pDbPath, 0o600)
    except OSError:
      pass
  return vDb


class RequestLogger:
  """SQLite based logger to keep track of the requests"""

  def __init__(self):
    vConfig = fGetConfig()
    self._vRetentionDays = vConfig.logging.retention_days
    self._vLock = threading.Lock()
    self._vDb = fOpenDatabase(vConfig.logging.database)
    self._mInitializeDatabase()

  def _mInitializeDatabase(self):
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute(f"""
          CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'route',
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            pii_detected INTEGER NOT NULL DEFAULT 0,
            entities TEXT,
            latency_ms INTEGER NOT NULL,
            scan_time_ms INTEGER NOT NULL DEFAULT 0,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            user_agent TEXT,
            language TEXT NOT NULL DEFAULT 'en',
            language_fallback INTEGER NOT NULL DEFAULT 0,
            detected_language TEXT,
            original_content TEXT,
            masked_content TEXT,
            created_at TEXT DEFAULT ({cSqliteStorageNow})
          )
        """)

        # Create indexes for performance
        vCursor.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON request_logs(timestamp)")
        vCursor.execute("CREATE INDEX IF NOT EXISTS idx_provider ON request_logs(provider)")
        vCursor.execute("CREATE INDEX IF NOT EXISTS idx_pii_detected ON request_logs(pii_detected)")
        self._vDb.commit()

        # Add columns when they do not exist (migrations)
        self._mAddOriginalContentColumnIfMissing(vCursor)
        self._mAddResponseColumnsIfMissing(vCursor)

        self._vDb.commit()
    except sqlite3.Error as vError:
      print(f"Error initializing the logs database: {vError}")
      raise

  def _mAddOriginalContentColumnIfMissing(self, pCursor):
    """Adds the original_content column when it does not exist (migration)"""
    pCursor.execute("PRAGMA table_info(request_logs)")
    aColumns = [vRow[1] for vRow in pCursor.fetchall()]
    if 'original_content' not in aColumns:
      try:
        pCursor.execute("ALTER TABLE request_logs ADD COLUMN original_content TEXT")
        self._vDb.commit()
      except Exception:
        pass

  def _mAddResponseColumnsIfMissing(self, pCursor):
    """Adds the provider_response and client_response columns when they do not exist (migration)"""
    pCursor.execute("PRAGMA table_info(request_logs)")
    aColumns = [vRow[1] for vRow in pCursor.fetchall()]
    if 'provider_response' not in aColumns:
      try:
        pCursor.execute("ALTER TABLE request_logs ADD COLUMN provider_response TEXT")
        self._vDb.commit()
      except Exception:
        pass
    if 'client_response' not in aColumns:
      try:
        pCursor.execute("ALTER TABLE request_logs ADD COLUMN client_response TEXT")
        self._vDb.commit()
      except Exception:
        pass

  def mRecord(self, pEntry: RequestRecord):
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("""
          INSERT INTO request_logs
            (timestamp, mode, provider, model, pii_detected, entities, latency_ms, scan_time_ms,
             prompt_tokens, completion_tokens, user_agent, language, language_fallback,
             detected_language, original_content, masked_content, provider_response,
             client_response)
          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
          pEntry.timestamp,
          pEntry.mode,
          pEntry.provider,
          pEntry.model,
          1 if pEntry.pii_detected else 0,
          pEntry.entities,
          pEntry.latency_ms,
          pEntry.scan_time_ms,
          pEntry.prompt_tokens,
          pEntry.completion_tokens,
          pEntry.user_agent,
          pEntry.language,
          1 if pEntry.language_fallback else 0,
          pEntry.detected_language,
          pEntry.original_content,
          pEntry.masked_content,
          pEntry.provider_response,
          pEntry.client_response
        ))
        self._vDb.commit()
    except sqlite3.Error as vError:
      print(f"Error recording the request in the database: {vError}")
      raise

  def mGetLogs(self, pLimit: int = 100, pOffset: int = 0) -> list[dict]:
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("""
          SELECT * FROM request_logs
          ORDER BY timestamp DESC
          LIMIT ? OFFSET ?
        """, (pLimit, pOffset))
        return [dict(vRow) for vRow in vCursor.fetchall()]
    except sqlite3.Error as vError:
      print(f"Error reading the logs: {vError}")
      return []

  def mGetStatistics(self) -> Statistics:
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()

        # Total requests
        vCursor.execute("SELECT COUNT(*) as count FROM request_logs")
        vTotal = vCursor.fetchone()["count"]

        # Requests with PII
        vCursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE pii_detected = 1")
        vPii = vCursor.fetchone()["count"]

        # Upstream vs Local
        vCursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE provider = 'upstream'")
        vUpstream = vCursor.fetchone()["count"]

        vCursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE provider = 'local'")
        vLocal = vCursor.fetchone()["count"]

        # Average scan time
        vCursor.execute("SELECT AVG(scan_time_ms) as avg FROM request_logs")
        vAvgScan = vCursor.fetchone()["avg"] or 0

        # Total tokens
        vCursor.execute("""
          SELECT COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) as total
          FROM request_logs
        """)
        vTotalTokens = vCursor.fetchone()["total"]

        # Requests of the last hour
        vOneHourAgo = fStorageAgo(pHours=1)
        vCursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE timestamp >= ?", (vOneHourAgo,))
        vHour = vCursor.fetchone()["count"]

      return Statistics(
        total_requests=vTotal,
        pii_requests=vPii,
        pii_percentage=round((vPii / vTotal) * 100, 1) if vTotal > 0 else 0,
        upstream_requests=vUpstream,
        local_requests=vLocal,
        avg_scan_time_ms=round(vAvgScan),
        total_tokens=vTotalTokens,
        requests_last_hour=vHour
      )
    except sqlite3.Error as vError:
      print(f"Error reading the statistics: {vError}")
      return Statistics()

  def mGetEntityStatistics(self) -> list[dict]:
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT entities FROM request_logs WHERE entities IS NOT NULL AND entities != ''")
        aRows = vCursor.fetchall()

      dEntityCount: dict[str, int] = {}
      for vRow in aRows:
        try:
          aEntities = [vEntity.strip() for vEntity in vRow["entities"].split(",") if vEntity.strip()]
          for vEntity in aEntities:
            dEntityCount[vEntity] = dEntityCount.get(vEntity, 0) + 1
        except (AttributeError, TypeError):
          continue

      return sorted(
        [{"entity": vKey, "count": vValue} for vKey, vValue in dEntityCount.items()],
        key=lambda pItem: pItem["count"],
        reverse=True
      )
    except sqlite3.Error as vError:
      print(f"Error reading the entity statistics: {vError}")
      return []

  def mCleanup(self) -> int:
    if self._vRetentionDays <= 0:
      return 0

    try:
      vCutoffDate = fStorageAgo(pDays=self._vRetentionDays)
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("DELETE FROM request_logs WHERE timestamp < ?", (vCutoffDate,))
        vDeleted = vCursor.rowcount
        self._vDb.commit()
      return vDeleted
    except sqlite3.Error as vError:
      print(f"Error cleaning the logs: {vError}")
      return 0

  def mClose(self):
    try:
      with self._vLock:
        self._vDb.close()
    except sqlite3.Error as vError:
      print(f"Error closing the logs database: {vError}")


# Singleton instance
_vLoggerInstance: Optional[RequestLogger] = None


def fGetLogger() -> RequestLogger:
  global _vLoggerInstance
  if _vLoggerInstance is None:
    _vLoggerInstance = RequestLogger()
  return _vLoggerInstance


@dataclass
class RequestLogData:
  timestamp: str
  mode: str
  provider: str
  model: str
  pii_detected: bool
  entities: list[str]
  latency_ms: int
  scan_time_ms: int
  prompt_tokens: Optional[int] = None
  completion_tokens: Optional[int] = None
  language: str = "en"
  language_fallback: bool = False
  detected_language: Optional[str] = None
  original_content: Optional[str] = None
  masked_content: Optional[str] = None
  provider_response: Optional[str] = None
  client_response: Optional[str] = None


def fLogRequest(pData: RequestLogData, pUserAgent: Optional[str]):
  try:
    vLogger = fGetLogger()
    vLogger.mRecord(RequestRecord(
      timestamp=pData.timestamp,
      mode=pData.mode,
      provider=pData.provider,
      model=pData.model,
      pii_detected=pData.pii_detected,
      entities=",".join(pData.entities),
      latency_ms=pData.latency_ms,
      scan_time_ms=pData.scan_time_ms,
      prompt_tokens=pData.prompt_tokens,
      completion_tokens=pData.completion_tokens,
      user_agent=pUserAgent,
      language=pData.language,
      language_fallback=pData.language_fallback,
      detected_language=pData.detected_language,
      original_content=pData.original_content,
      masked_content=pData.masked_content,
      provider_response=pData.provider_response,
      client_response=pData.client_response
    ))
  except Exception as vError:
    print(f"The request could not be recorded: {vError}")
