#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Dashboard users and their sessions.

Passwords are stored as PBKDF2-SHA256 hashes. Sessions are random tokens: the
browser keeps the token in a cookie and the database only keeps its SHA-256,
so a copy of the database does not hand out valid sessions.

Every user can have one recovery code, shown only once, that sets a new
password at /auth/recover/ without an administrator. Like the session tokens,
only its SHA-256 is stored, and it is spent (replaced by a new one) when used.
"""

import hashlib
import hmac
import re
import secrets
import sqlite3
import threading
from typing import Optional

from config import fGetConfig
from services.dates import cSqliteStorageNow, fNowStorage, fStorageFromNow
from services.logger import fOpenDatabase


cRoleAdmin = "admin"
cRoleUser = "user"
cRoles = (cRoleAdmin, cRoleUser)

cPasswordHashAlgorithm = "pbkdf2_sha256"
cPasswordHashIterations = 600000
cMinimumPasswordLength = 8
cUsernamePattern = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Recovery codes: 20 characters of an alphabet without the ones that are easy to
# confuse (0/O, 1/I), shown in groups of 5. 20 characters out of 32 are 100
# random bits, so a plain SHA-256 is enough to store them.
cRecoveryCodeAlphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
cRecoveryCodeLength = 20
cRecoveryCodeGroupLength = 5
cRecoveryCodeSeparatorPattern = re.compile(r"[\s-]+")


class UserError(ValueError):
  """Error caused by the data of a user (shown to whoever made the request)"""


def fHashPassword(pPassword: str) -> str:
  """Returns the PBKDF2-SHA256 hash of a password, with its salt and iterations"""
  vSalt = secrets.token_hex(16)
  vHash = hashlib.pbkdf2_hmac("sha256", pPassword.encode("utf-8"), bytes.fromhex(vSalt), cPasswordHashIterations)
  return f"{cPasswordHashAlgorithm}${cPasswordHashIterations}${vSalt}${vHash.hex()}"


def fVerifyPassword(pPassword: str, pStoredHash: str) -> bool:
  """Checks a password against a stored hash, in constant time"""
  try:
    vAlgorithm, vIterations, vSalt, vHash = pStoredHash.split("$", 3)
    if vAlgorithm != cPasswordHashAlgorithm:
      return False
    vCandidate = hashlib.pbkdf2_hmac("sha256", pPassword.encode("utf-8"), bytes.fromhex(vSalt), int(vIterations))
    return hmac.compare_digest(vCandidate.hex(), vHash)
  except (ValueError, AttributeError):
    return False


def fHashToken(pToken: str) -> str:
  return hashlib.sha256(pToken.encode("utf-8")).hexdigest()


def fGenerateRecoveryCode() -> str:
  """Returns a new recovery code, such as ABCDE-FGHJK-LMNPQ-RSTUV"""
  vRaw = "".join(secrets.choice(cRecoveryCodeAlphabet) for vPosition in range(cRecoveryCodeLength))
  aGroups = [vRaw[vStart:vStart + cRecoveryCodeGroupLength] for vStart in range(0, cRecoveryCodeLength, cRecoveryCodeGroupLength)]
  return "-".join(aGroups)


def fNormalizeRecoveryCode(pCode: str) -> str:
  """Upper case and without spaces or hyphens, so the code can be typed in any way"""
  if not isinstance(pCode, str):
    return ""
  return cRecoveryCodeSeparatorPattern.sub("", pCode).upper()


def fHashRecoveryCode(pCode: str) -> str:
  return hashlib.sha256(fNormalizeRecoveryCode(pCode).encode("utf-8")).hexdigest()


def fValidateUsername(pUsername: str):
  if not isinstance(pUsername, str) or not cUsernamePattern.match(pUsername):
    raise UserError("invalid_username")


def fValidatePassword(pPassword: str):
  if not isinstance(pPassword, str) or len(pPassword) < cMinimumPasswordLength:
    raise UserError("password_too_short")


def fValidateRole(pRole: str):
  if pRole not in cRoles:
    raise UserError("invalid_role")


class UserStore:
  """Users and sessions of the dashboards, in the application database"""

  def __init__(self):
    vConfig = fGetConfig()
    self._vSessionHours = vConfig.dashboard.session_hours
    self._vDummyHash: Optional[str] = None
    self._vLock = threading.Lock()
    self._vDb = fOpenDatabase(vConfig.logging.database)
    self._mInitializeDatabase()

  def _mInitializeDatabase(self):
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute(f"""
          CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT ({cSqliteStorageNow}),
            updated_at TEXT NOT NULL DEFAULT ({cSqliteStorageNow}),
            recovery_code_hash TEXT,
            recovery_code_created_at TEXT
          )
        """)
        # Databases created before the recovery codes get their columns here
        vCursor.execute("PRAGMA table_info(users)")
        sColumns = {vRow["name"] for vRow in vCursor.fetchall()}
        if "recovery_code_hash" not in sColumns:
          vCursor.execute("ALTER TABLE users ADD COLUMN recovery_code_hash TEXT")
        if "recovery_code_created_at" not in sColumns:
          vCursor.execute("ALTER TABLE users ADD COLUMN recovery_code_created_at TEXT")
        vCursor.execute(f"""
          CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT ({cSqliteStorageNow})
          )
        """)
        vCursor.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)")
        self._vDb.commit()
    except sqlite3.Error as vError:
      print(f"Error initializing the users tables: {vError}")
      raise

  def _mRowToUser(self, pRow) -> Optional[dict]:
    if pRow is None:
      return None
    return {
      "id": pRow["id"],
      "username": pRow["username"],
      "role": pRow["role"],
      "created_at": pRow["created_at"],
      "updated_at": pRow["updated_at"],
      "has_recovery_code": bool(pRow["recovery_code_hash"]),
      "recovery_code_created_at": pRow["recovery_code_created_at"]
    }

  def mGetUser(self, pUsername: str) -> Optional[dict]:
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT * FROM users WHERE username = ?", (pUsername,))
        return self._mRowToUser(vCursor.fetchone())
    except sqlite3.Error as vError:
      print(f"Error reading the user {pUsername}: {vError}")
      return None

  def mUserExists(self, pUsername: str) -> bool:
    return self.mGetUser(pUsername) is not None

  def mListUsers(self) -> list[dict]:
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT * FROM users ORDER BY username")
        return [self._mRowToUser(vRow) for vRow in vCursor.fetchall()]
    except sqlite3.Error as vError:
      print(f"Error reading the users: {vError}")
      return []

  def _mCountAdmins(self, pCursor) -> int:
    pCursor.execute("SELECT COUNT(*) AS count FROM users WHERE role = ?", (cRoleAdmin,))
    return pCursor.fetchone()["count"]

  def mCreateUser(self, pUsername: str, pPassword: str, pRole: str) -> dict:
    fValidateUsername(pUsername)
    fValidatePassword(pPassword)
    fValidateRole(pRole)
    vHash = fHashPassword(pPassword)
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute(
          "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
          (pUsername, vHash, pRole)
        )
        self._vDb.commit()
    except sqlite3.IntegrityError as vError:
      raise UserError("user_exists") from vError
    return self.mGetUser(pUsername)

  def mSetPassword(self, pUsername: str, pPassword: str):
    fValidatePassword(pPassword)
    vHash = fHashPassword(pPassword)
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute(
        "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
        (vHash, fNowStorage(), pUsername)
      )
      if vCursor.rowcount == 0:
        raise UserError("user_not_found")
      self._vDb.commit()

  def mSetUser(self, pUsername: str, pPassword: str, pRole: str) -> str:
    """Creates the user, or updates its password and role. Returns 'created' or 'updated'."""
    fValidateUsername(pUsername)
    fValidateRole(pRole)
    if not self.mUserExists(pUsername):
      self.mCreateUser(pUsername, pPassword, pRole)
      return "created"
    self.mSetPassword(pUsername, pPassword)
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute("UPDATE users SET role = ?, updated_at = ? WHERE username = ?", (pRole, fNowStorage(), pUsername))
      self._vDb.commit()
    return "updated"

  def mDeleteUser(self, pUsername: str):
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute("SELECT id, role FROM users WHERE username = ?", (pUsername,))
      vRow = vCursor.fetchone()
      if vRow is None:
        raise UserError("user_not_found")
      if vRow["role"] == cRoleAdmin and self._mCountAdmins(vCursor) <= 1:
        raise UserError("last_admin")
      vCursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (vRow["id"],))
      vCursor.execute("DELETE FROM users WHERE id = ?", (vRow["id"],))
      self._vDb.commit()

  def mAuthenticate(self, pUsername: str, pPassword: str) -> Optional[dict]:
    """Returns the user when the credentials are right, or None"""
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT * FROM users WHERE username = ?", (pUsername,))
        vRow = vCursor.fetchone()
    except sqlite3.Error as vError:
      print(f"Error authenticating {pUsername}: {vError}")
      return None

    if vRow is None:
      # Same work as a real check, so the answer time does not reveal which users exist
      if self._vDummyHash is None:
        self._vDummyHash = fHashPassword(secrets.token_hex(16))
      fVerifyPassword(pPassword, self._vDummyHash)
      return None
    if not fVerifyPassword(pPassword, vRow["password_hash"]):
      return None
    return self._mRowToUser(vRow)

  def mNewRecoveryCode(self, pUsername: str) -> str:
    """Gives the user a new recovery code (the previous one stops working) and returns it"""
    vCode = fGenerateRecoveryCode()
    vNow = fNowStorage()
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute(
        "UPDATE users SET recovery_code_hash = ?, recovery_code_created_at = ?, updated_at = ? WHERE username = ?",
        (fHashRecoveryCode(vCode), vNow, vNow, pUsername)
      )
      if vCursor.rowcount == 0:
        raise UserError("user_not_found")
      self._vDb.commit()
    return vCode

  def mRecoverPassword(self, pUsername: str, pCode: str, pNewPassword: str) -> Optional[str]:
    """
    Sets a new password with the recovery code of the user. A right code is
    spent: every session of the user is closed and a new code is returned.
    Returns None when the user does not exist or the code is wrong.
    """
    fValidatePassword(pNewPassword)
    vCodeHash = fHashRecoveryCode(pCode)
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("SELECT id, recovery_code_hash FROM users WHERE username = ?", (pUsername,))
        vRow = vCursor.fetchone()
    except sqlite3.Error as vError:
      print(f"Error reading the recovery code of {pUsername}: {vError}")
      return None

    vStoredHash = vRow["recovery_code_hash"] if vRow is not None else None
    # Compared even when there is nothing to compare with, so the answer time
    # does not reveal which users exist or have a code
    vMatches = hmac.compare_digest(vCodeHash, vStoredHash or "0" * len(vCodeHash))
    if vRow is None or not vStoredHash or not fNormalizeRecoveryCode(pCode) or not vMatches:
      return None

    # The slow hash is calculated outside the lock
    vPasswordHash = fHashPassword(pNewPassword)
    vNewCode = fGenerateRecoveryCode()
    vNow = fNowStorage()
    with self._vLock:
      vCursor = self._vDb.cursor()
      # The code must still be the same one: two requests with the same code cannot both win
      vCursor.execute(
        "UPDATE users SET password_hash = ?, recovery_code_hash = ?, recovery_code_created_at = ?, updated_at = ? "
        "WHERE id = ? AND recovery_code_hash = ?",
        (vPasswordHash, fHashRecoveryCode(vNewCode), vNow, vNow, vRow["id"], vStoredHash)
      )
      if vCursor.rowcount == 0:
        self._vDb.rollback()
        return None
      vCursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (vRow["id"],))
      self._vDb.commit()
    return vNewCode

  def mCreateSession(self, pUserId: int) -> str:
    """Creates a session and returns its token (only the browser keeps it)"""
    vToken = secrets.token_urlsafe(32)
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute("DELETE FROM user_sessions WHERE expires_at < ?", (fNowStorage(),))
      vCursor.execute(
        "INSERT INTO user_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (pUserId, fHashToken(vToken), fStorageFromNow(pHours=self._vSessionHours))
      )
      self._vDb.commit()
    return vToken

  def mGetSessionUser(self, pToken: Optional[str]) -> Optional[dict]:
    """Returns the user of a valid session token, or None"""
    if not pToken:
      return None
    try:
      with self._vLock:
        vCursor = self._vDb.cursor()
        vCursor.execute("""
          SELECT u.* FROM user_sessions s
          JOIN users u ON u.id = s.user_id
          WHERE s.token_hash = ? AND s.expires_at > ?
        """, (fHashToken(pToken), fNowStorage()))
        return self._mRowToUser(vCursor.fetchone())
    except sqlite3.Error as vError:
      print(f"Error reading the session: {vError}")
      return None

  def mDeleteSession(self, pToken: Optional[str]):
    if not pToken:
      return
    with self._vLock:
      vCursor = self._vDb.cursor()
      vCursor.execute("DELETE FROM user_sessions WHERE token_hash = ?", (fHashToken(pToken),))
      self._vDb.commit()

  def mDeleteUserSessions(self, pUserId: int, pExceptToken: Optional[str] = None):
    with self._vLock:
      vCursor = self._vDb.cursor()
      if pExceptToken:
        vCursor.execute(
          "DELETE FROM user_sessions WHERE user_id = ? AND token_hash != ?",
          (pUserId, fHashToken(pExceptToken))
        )
      else:
        vCursor.execute("DELETE FROM user_sessions WHERE user_id = ?", (pUserId,))
      self._vDb.commit()

  def mClose(self):
    try:
      with self._vLock:
        self._vDb.close()
    except sqlite3.Error as vError:
      print(f"Error closing the users database: {vError}")


# Singleton instance
_vUserStoreInstance: Optional[UserStore] = None


def fGetUserStore() -> UserStore:
  global _vUserStoreInstance
  if _vUserStoreInstance is None:
    _vUserStoreInstance = UserStore()
  return _vUserStoreInstance
