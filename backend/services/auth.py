#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Authentication helpers shared by the page routes and the API routes.
"""

from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from config import fGetConfig
from services.users import cRoleAdmin, fGetUserStore


cSessionCookie = "ainonyproxy_session"
cLoginPath = "/auth/login/"
cAdminDashboardPath = "/admin/dashboard/"
cUserDashboardPath = "/user/dashboard/"


def fGetSessionToken(pRequest: Request) -> Optional[str]:
  return pRequest.cookies.get(cSessionCookie)


def fGetCurrentUser(pRequest: Request) -> Optional[dict]:
  """Returns the user of the session of the request, or None"""
  try:
    return fGetUserStore().mGetSessionUser(fGetSessionToken(pRequest))
  except Exception as vError:
    print(f"[AUTH] Error reading the session: {vError}")
    return None


def fIsAdmin(pUser: Optional[dict]) -> bool:
  return bool(pUser) and pUser.get("role") == cRoleAdmin


def fIsSafeNextPath(pPath: Optional[str]) -> bool:
  """Only paths of this same site are accepted as a destination after the login"""
  if not pPath or not isinstance(pPath, str):
    return False
  if not pPath.startswith("/") or pPath.startswith("//") or "\\" in pPath:
    return False
  return True


def fHomePathFor(pUser: Optional[dict]) -> str:
  """Dashboard that corresponds to a user"""
  return cAdminDashboardPath if fIsAdmin(pUser) else cUserDashboardPath


def fLoginRedirect(pRequest: Request) -> RedirectResponse:
  """Sends to the login form, remembering the page that was requested"""
  vNext = pRequest.url.path
  if pRequest.url.query:
    vNext += f"?{pRequest.url.query}"
  return RedirectResponse(url=f"{cLoginPath}?next={quote(vNext, safe='')}", status_code=303)


def fRequireApiUser(pRequest: Request) -> dict:
  """API guard: any logged in user"""
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    raise HTTPException(status_code=401, detail={"error": {"message": "Authentication required", "type": "unauthorized"}})
  return vUser


def fRequireApiAdmin(pRequest: Request) -> dict:
  """API guard: only administrators"""
  vUser = fRequireApiUser(pRequest)
  if not fIsAdmin(vUser):
    raise HTTPException(status_code=403, detail={"error": {"message": "Administrator role required", "type": "forbidden"}})
  return vUser


def fSetSessionCookie(pResponse, pToken: str):
  """The cookie only travels over HTTPS, is invisible to JavaScript and never leaves this site"""
  vConfig = fGetConfig()
  pResponse.set_cookie(
    key=cSessionCookie,
    value=pToken,
    max_age=vConfig.dashboard.session_hours * 3600,
    path="/",
    secure=True,
    httponly=True,
    samesite="strict"
  )


def fClearSessionCookie(pResponse):
  pResponse.delete_cookie(key=cSessionCookie, path="/", secure=True, httponly=True, samesite="strict")
