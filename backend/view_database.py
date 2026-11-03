#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Script that shows the content of the ainonyproxy database.

Usage (as root or as the ainonyproxy user):
  python3 view_database.py

It shows an interactive menu to explore the different tables.
"""

import os
import sys
import sqlite3
from pathlib import Path

# Add the backend folder to the path so the project modules can be imported
vBackendDir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, vBackendDir)

from config import fGetConfig
from services.dates import fStorageToDisplay


def fConnectDatabase():
  """Connects to the SQLite database and returns the connection"""
  vConfig = fGetConfig()
  vDbPath = vConfig.logging.database
  if not Path(vDbPath).exists():
    print(f"\n  Error: the database was not found in: {vDbPath}")
    print("  Make sure the server has been started at least once.\n")
    sys.exit(1)
  try:
    vDb = sqlite3.connect(vDbPath)
    vDb.row_factory = sqlite3.Row
    return vDb
  except sqlite3.Error as vError:
    print(f"\n  Error connecting to the database: {vError}\n")
    sys.exit(1)


def fGetTables(pDb):
  """Returns the list of tables of the database"""
  vCursor = pDb.cursor()
  vCursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
  aTables = [vRow["name"] for vRow in vCursor.fetchall()]
  return aTables


def fShowUsers(pDb):
  """Shows every user with its main data"""
  vCursor = pDb.cursor()
  vCursor.execute("SELECT id, username, role, created_at, updated_at FROM users ORDER BY id")
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no registered users.\n")
    return
  print("\n  === USERS ===\n")
  print(f"  {'ID':<6}{'Username':<30}{'Role':<10}{'Created':<27}{'Updated'}")
  print(f"  {'-'*6}{'-'*30}{'-'*10}{'-'*27}{'-'*25}")
  for vRow in aRows:
    vCreated = fStorageToDisplay(vRow["created_at"] or "")
    vUpdated = fStorageToDisplay(vRow["updated_at"] or "")
    print(f"  {vRow['id']:<6}{vRow['username']:<30}{vRow['role']:<10}{vCreated:<27}{vUpdated}")
  print(f"\n  Total: {len(aRows)} user(s)\n")


def fShowUserApiKeys(pDb):
  """Shows the API keys of each user (without showing the encrypted key)"""
  vCursor = pDb.cursor()
  vCursor.execute("""
    SELECT k.id, u.username, k.provider, k.created_at, k.updated_at
    FROM user_api_keys k
    JOIN users u ON k.user_id = u.id
    ORDER BY u.username, k.provider
  """)
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no API keys configured.\n")
    return
  print("\n  === API KEYS PER USER ===\n")
  print(f"  {'ID':<6}{'Username':<30}{'Provider':<15}{'Created':<27}{'Updated'}")
  print(f"  {'-'*6}{'-'*30}{'-'*15}{'-'*27}{'-'*25}")
  for vRow in aRows:
    vCreated = fStorageToDisplay(vRow["created_at"] or "")
    vUpdated = fStorageToDisplay(vRow["updated_at"] or "")
    print(f"  {vRow['id']:<6}{vRow['username']:<30}{vRow['provider']:<15}{vCreated:<27}{vUpdated}")
  print(f"\n  Total: {len(aRows)} API key(s)\n")


def fShowActiveSessions(pDb):
  """Shows the sessions of the users"""
  vCursor = pDb.cursor()
  vCursor.execute("""
    SELECT s.id, u.username, s.expires_at, s.created_at
    FROM user_sessions s
    JOIN users u ON s.user_id = u.id
    ORDER BY s.created_at DESC
  """)
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no registered sessions.\n")
    return
  print("\n  === ACTIVE SESSIONS ===\n")
  print(f"  {'ID':<6}{'Username':<30}{'Expires':<27}{'Created'}")
  print(f"  {'-'*6}{'-'*30}{'-'*27}{'-'*25}")
  for vRow in aRows:
    vExpires = fStorageToDisplay(vRow["expires_at"] or "")
    vCreated = fStorageToDisplay(vRow["created_at"] or "")
    print(f"  {vRow['id']:<6}{vRow['username']:<30}{vExpires:<27}{vCreated}")
  print(f"\n  Total: {len(aRows)} session(s)\n")


def fShowApiTokens(pDb):
  """Shows the API authentication tokens of each user"""
  vCursor = pDb.cursor()
  vCursor.execute("""
    SELECT t.id, u.username, t.name, t.is_active, t.last_used_at, t.created_at
    FROM api_auth_tokens t
    JOIN users u ON t.user_id = u.id
    ORDER BY u.username, t.created_at DESC
  """)
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no registered API tokens.\n")
    return
  print("\n  === API TOKENS ===\n")
  print(f"  {'ID':<6}{'Username':<30}{'Name':<20}{'Active':<10}{'Last use':<27}{'Created'}")
  print(f"  {'-'*6}{'-'*30}{'-'*20}{'-'*10}{'-'*27}{'-'*25}")
  for vRow in aRows:
    vActive = "Yes" if vRow["is_active"] else "No"
    vName = vRow["name"] or "(no name)"
    vLastUse = fStorageToDisplay(vRow["last_used_at"]) if vRow["last_used_at"] else "Never"
    vCreated = fStorageToDisplay(vRow["created_at"] or "")
    print(f"  {vRow['id']:<6}{vRow['username']:<30}{vName:<20}{vActive:<10}{vLastUse:<27}{vCreated}")
  print(f"\n  Total: {len(aRows)} token(s)\n")


def fShowRecentLogs(pDb, pLimit=20):
  """Shows the most recent request logs"""
  vCursor = pDb.cursor()
  vCursor.execute("""
    SELECT id, timestamp, provider, model, pii_detected, entities, latency_ms, scan_time_ms, language
    FROM request_logs
    ORDER BY timestamp DESC
    LIMIT ?
  """, (pLimit,))
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no request logs.\n")
    return
  print(f"\n  === LAST {pLimit} REQUEST LOGS ===\n")
  print(f"  {'ID':<6}{'Timestamp':<26}{'Provider':<12}{'Model':<20}{'PII':<6}{'Entities':<25}{'Lat(ms)':<10}{'Scan(ms)':<10}{'Language'}")
  print(f"  {'-'*6}{'-'*26}{'-'*12}{'-'*20}{'-'*6}{'-'*25}{'-'*10}{'-'*10}{'-'*8}")
  for vRow in aRows:
    vPii = "Yes" if vRow["pii_detected"] else "No"
    vEntities = vRow["entities"] or ""
    if len(vEntities) > 23:
      vEntities = vEntities[:20] + "..."
    vModel = vRow["model"] or ""
    if len(vModel) > 18:
      vModel = vModel[:15] + "..."
    vTimestamp = fStorageToDisplay(vRow["timestamp"] or "")
    print(f"  {vRow['id']:<6}{vTimestamp:<26}{vRow['provider']:<12}{vModel:<20}{vPii:<6}{vEntities:<25}{vRow['latency_ms']:<10}{vRow['scan_time_ms']:<10}{vRow['language']}")
  print(f"\n  Total shown: {len(aRows)}\n")


def fShowStatistics(pDb):
  """Shows general statistics of the database"""
  vCursor = pDb.cursor()
  print("\n  === GENERAL STATISTICS ===\n")

  # Total requests
  vCursor.execute("SELECT COUNT(*) as count FROM request_logs")
  vTotalLogs = vCursor.fetchone()["count"]
  print(f"  Total requests:                  {vTotalLogs}")

  # Requests with PII
  vCursor.execute("SELECT COUNT(*) as count FROM request_logs WHERE pii_detected = 1")
  vWithPii = vCursor.fetchone()["count"]
  vPiiPercentage = round((vWithPii / vTotalLogs) * 100, 1) if vTotalLogs > 0 else 0
  print(f"  Requests with PII detected:      {vWithPii} ({vPiiPercentage}%)")

  # Average scan time
  vCursor.execute("SELECT AVG(scan_time_ms) as avg FROM request_logs")
  vAvgScan = vCursor.fetchone()["avg"] or 0
  print(f"  Average scan time:               {round(vAvgScan)} ms")

  # Average latency
  vCursor.execute("SELECT AVG(latency_ms) as avg FROM request_logs")
  vAvgLatency = vCursor.fetchone()["avg"] or 0
  print(f"  Average latency:                 {round(vAvgLatency)} ms")

  # Total tokens
  vCursor.execute("""
    SELECT COALESCE(SUM(COALESCE(prompt_tokens, 0) + COALESCE(completion_tokens, 0)), 0) as total
    FROM request_logs
  """)
  vTotalTokens = vCursor.fetchone()["total"]
  print(f"  Total tokens used:               {vTotalTokens}")

  # Requests per provider
  vCursor.execute("SELECT provider, COUNT(*) as count FROM request_logs GROUP BY provider ORDER BY count DESC")
  aProviders = vCursor.fetchall()
  if aProviders:
    print(f"\n  Requests per provider:")
    for vProvider in aProviders:
      print(f"    {vProvider['provider']:<20} {vProvider['count']}")

  # Requests per language
  vCursor.execute("SELECT language, COUNT(*) as count FROM request_logs GROUP BY language ORDER BY count DESC")
  aLanguages = vCursor.fetchall()
  if aLanguages:
    print(f"\n  Requests per language:")
    for vLanguage in aLanguages:
      print(f"    {vLanguage['language']:<20} {vLanguage['count']}")

  # Most frequent PII entities
  vCursor.execute("SELECT entities FROM request_logs WHERE entities IS NOT NULL AND entities != ''")
  dEntityCount = {}
  for vRow in vCursor.fetchall():
    try:
      aEntities = [vEntity.strip() for vEntity in vRow["entities"].split(",") if vEntity.strip()]
      for vEntity in aEntities:
        dEntityCount[vEntity] = dEntityCount.get(vEntity, 0) + 1
    except (AttributeError, TypeError):
      continue
  if dEntityCount:
    aSorted = sorted(dEntityCount.items(), key=lambda pItem: pItem[1], reverse=True)
    print(f"\n  Most detected PII entities:")
    for vEntity, vCount in aSorted[:10]:
      print(f"    {vEntity:<25} {vCount}")

  # Registered users
  try:
    vCursor.execute("SELECT COUNT(*) as count FROM users")
    vTotalUsers = vCursor.fetchone()["count"]
    print(f"\n  Registered users:                {vTotalUsers}")
  except sqlite3.OperationalError:
    pass

  print()


def fShowLogDetail(pDb):
  """Shows the full detail of a specific log"""
  try:
    vIdText = input("\n  Type the ID of the log to show: ").strip()
  except EOFError:
    return
  if not vIdText.isdigit():
    print("  Invalid ID.\n")
    return
  vId = int(vIdText)
  vCursor = pDb.cursor()
  vCursor.execute("SELECT * FROM request_logs WHERE id = ?", (vId,))
  vRow = vCursor.fetchone()
  if not vRow:
    print(f"\n  No log was found with the ID {vId}.\n")
    return
  print(f"\n  === DETAIL OF THE LOG #{vId} ===\n")
  for vKey in vRow.keys():
    vValue = vRow[vKey]
    if vValue is None:
      vValue = "(null)"
    elif vKey in ("timestamp", "created_at"):
      vValue = fStorageToDisplay(vValue)
    elif isinstance(vValue, str) and len(vValue) > 200:
      vValue = vValue[:200] + "... (truncated)"
    print(f"  {vKey:<25} {vValue}")
  print()


def fShowMaskedContent(pDb, pLimit=10):
  """Shows the last logs that had PII, with their original and masked content"""
  vCursor = pDb.cursor()
  vCursor.execute("""
    SELECT id, timestamp, provider, original_content, masked_content, entities
    FROM request_logs
    WHERE pii_detected = 1 AND (original_content IS NOT NULL OR masked_content IS NOT NULL)
    ORDER BY timestamp DESC
    LIMIT ?
  """, (pLimit,))
  aRows = vCursor.fetchall()
  if not aRows:
    print("\n  There are no logs with masked content.\n")
    return
  print(f"\n  === LAST {pLimit} MASKINGS ===\n")
  for vRow in aRows:
    print(f"  --- Log #{vRow['id']} | {fStorageToDisplay(vRow['timestamp'] or '')} | {vRow['provider']} ---")
    print(f"  Entities: {vRow['entities']}")
    vOriginal = vRow["original_content"] or "(not logged: log_content is false)"
    vMasked = vRow["masked_content"] or "(not logged: log_masked_content is false)"
    if len(vOriginal) > 300:
      vOriginal = vOriginal[:300] + "... (truncated)"
    if len(vMasked) > 300:
      vMasked = vMasked[:300] + "... (truncated)"
    print(f"  Original:    {vOriginal}")
    print(f"  Masked:      {vMasked}")
    print()


def fShowMenu():
  """Shows the main menu"""
  print("\n  ========================================")
  print("  ainonyproxy - Database viewer")
  print("  ========================================\n")
  print("  1. Users")
  print("  2. API keys per user")
  print("  3. Active sessions")
  print("  4. API tokens")
  print("  5. Recent logs (last 20)")
  print("  6. Recent logs (last 100)")
  print("  7. Detail of a specific log")
  print("  8. Original vs masked content")
  print("  9. General statistics")
  print("  0. Exit")
  print()


def fMain():
  vDb = fConnectDatabase()
  aTables = fGetTables(vDb)

  while True:
    fShowMenu()
    try:
      vOption = input("  Choose an option: ").strip()
    except EOFError:
      vOption = "0"

    try:
      if vOption == "1":
        if "users" in aTables:
          fShowUsers(vDb)
        else:
          print("\n  The 'users' table does not exist. Start the server once to create it.\n")

      elif vOption == "2":
        if "user_api_keys" in aTables:
          fShowUserApiKeys(vDb)
        else:
          print("\n  The 'user_api_keys' table does not exist.\n")

      elif vOption == "3":
        if "user_sessions" in aTables:
          fShowActiveSessions(vDb)
        else:
          print("\n  The 'user_sessions' table does not exist.\n")

      elif vOption == "4":
        if "api_auth_tokens" in aTables:
          fShowApiTokens(vDb)
        else:
          print("\n  The 'api_auth_tokens' table does not exist.\n")

      elif vOption == "5":
        if "request_logs" in aTables:
          fShowRecentLogs(vDb, 20)
        else:
          print("\n  The 'request_logs' table does not exist.\n")

      elif vOption == "6":
        if "request_logs" in aTables:
          fShowRecentLogs(vDb, 100)
        else:
          print("\n  The 'request_logs' table does not exist.\n")

      elif vOption == "7":
        if "request_logs" in aTables:
          fShowLogDetail(vDb)
        else:
          print("\n  The 'request_logs' table does not exist.\n")

      elif vOption == "8":
        if "request_logs" in aTables:
          fShowMaskedContent(vDb)
        else:
          print("\n  The 'request_logs' table does not exist.\n")

      elif vOption == "9":
        if "request_logs" in aTables:
          fShowStatistics(vDb)
        else:
          print("\n  The 'request_logs' table does not exist.\n")

      elif vOption == "0":
        print("\n  Bye.\n")
        vDb.close()
        sys.exit(0)

      else:
        print("\n  Invalid option.\n")
    except sqlite3.Error as vError:
      print(f"\n  Database error: {vError}\n")


if __name__ == "__main__":
  try:
    fMain()
  except KeyboardInterrupt:
    print()
    sys.exit(130)
