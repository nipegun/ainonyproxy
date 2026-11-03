#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Settings that the administrators change from their dashboard.

They live in the application database (table app_settings) and not in
config.json, so saving them never rewrites the configuration files that the
user edits by hand (and their ${VAR} references).
"""

import sqlite3
import threading
from typing import Optional

from config import fGetConfig
from services.dates import cSqliteStorageNow, fNowStorage
from services.logger import fOpenDatabase


# Whether anybody can create an account at /auth/register/
cSettingRegistrationOpen = "registration_open"

# Value of each setting while nobody has changed it
dSettingDefaults = {
  cSettingRegistrationOpen: True
}


class SettingsStore:
  """Key/value settings of the application, in the application database"""

  def __init__(self):
    self._vLock = threading.Lock()
    self._vDb = fOpenDatabase(fGetConfig().logging.database)
    self._mInitializeDatabase()

  def _mInitializeDatabase(self):
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute(f"""
          CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT ({cSqliteStorageNow})
          )
        """)
        self._vDb.commit()
    except sqlite3.Error as vError:
      print(f"Error initializing the settings table: {vError}")
      raise

  def mGetBool(self, pKey: str) -> bool:
    """Value of a yes/no setting, or its default when nobody has changed it"""
    vDefault = bool(dSettingDefaults.get(pKey, False))
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT value FROM app_settings WHERE key = ?", (pKey,))
        vRow = vCursor.fetchone()
    except sqlite3.Error as vError:
      print(f"Error reading the setting {pKey}: {vError}")
      return vDefault
    if vRow is None:
      return vDefault
    return vRow["value"] == "true"

  def mSetBool(self, pKey: str, pValue: bool):
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute(
          "INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?) "
          "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
          (pKey, "true" if pValue else "false", fNowStorage())
        )
        self._vDb.commit()
    except sqlite3.Error as vError:
      print(f"Error saving the setting {pKey}: {vError}")
      raise

  def mIsRegistrationOpen(self) -> bool:
    return self.mGetBool(cSettingRegistrationOpen)

  def mSetRegistrationOpen(self, pOpen: bool):
    self.mSetBool(cSettingRegistrationOpen, pOpen)

  def mClose(self):
    try:
      with self._vLock:
        self._vDb.close()
    except sqlite3.Error as vError:
      print(f"Error closing the settings database: {vError}")


# Singleton instance
_vSettingsStoreInstance: Optional[SettingsStore] = None


def fGetSettingsStore() -> SettingsStore:
  global _vSettingsStoreInstance
  if _vSettingsStoreInstance is None:
    _vSettingsStoreInstance = SettingsStore()
  return _vSettingsStoreInstance
