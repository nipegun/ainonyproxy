#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from config import cFrontendDir
from services.auth import (
  fClearSessionCookie,
  fGetCurrentUser,
  fGetSessionToken,
  fHomePathFor,
  fIsSafeNextPath,
  fRequireApiUser,
  fSetSessionCookie
)
from services.settings import fGetSettingsStore
from services.users import UserError, cRoleUser, fGetUserStore
from routes.users import fUserErrorToHttp

vAuthPagesRouter = APIRouter(include_in_schema=False)
vAuthApiRouter = APIRouter(tags=["auth"])

cTemplates = Jinja2Templates(directory=str(cFrontendDir / "templates"))

# Brute force brake: failed logins (and failed recoveries) allowed per client
# address inside the window
cMaxFailedLogins = 5
cFailedLoginWindowSeconds = 15 * 60
dFailedLogins: dict[str, list[float]] = {}
vFailedLoginsLock = threading.Lock()

# Registration brake: accounts that one client address can create inside the window
cMaxRegistrations = 5
cRegistrationWindowSeconds = 60 * 60
dRegistrations: dict[str, list[float]] = {}
vRegistrationsLock = threading.Lock()


class LoginSchema(BaseModel):
  username: str
  password: str
  next: Optional[str] = None


class RegisterSchema(BaseModel):
  username: str
  password: str


class RecoverSchema(BaseModel):
  username: str
  recovery_code: str
  new_password: str


def fClientAddress(pRequest: Request) -> str:
  return pRequest.client.host if pRequest.client else "unknown"


def fRecentFailures(pAddress: str) -> int:
  vNow = time.monotonic()
  with vFailedLoginsLock:
    aAttempts = [vMoment for vMoment in dFailedLogins.get(pAddress, []) if vNow - vMoment < cFailedLoginWindowSeconds]
    if aAttempts:
      dFailedLogins[pAddress] = aAttempts
    else:
      dFailedLogins.pop(pAddress, None)
    return len(aAttempts)


def fRememberFailure(pAddress: str):
  with vFailedLoginsLock:
    dFailedLogins.setdefault(pAddress, []).append(time.monotonic())


def fForgetFailures(pAddress: str):
  with vFailedLoginsLock:
    dFailedLogins.pop(pAddress, None)


def fRecentRegistrations(pAddress: str) -> int:
  vNow = time.monotonic()
  with vRegistrationsLock:
    aMoments = [vMoment for vMoment in dRegistrations.get(pAddress, []) if vNow - vMoment < cRegistrationWindowSeconds]
    if aMoments:
      dRegistrations[pAddress] = aMoments
    else:
      dRegistrations.pop(pAddress, None)
    return len(aMoments)


def fRememberRegistration(pAddress: str):
  with vRegistrationsLock:
    dRegistrations.setdefault(pAddress, []).append(time.monotonic())


@vAuthPagesRouter.get("/auth/login/", response_class=HTMLResponse)
def fLoginPage(pRequest: Request, pNext: Optional[str] = Query(default=None, alias="next")):
  """Login form"""
  vNext = pNext if fIsSafeNextPath(pNext) else ""
  vUser = fGetCurrentUser(pRequest)
  if vUser:
    return RedirectResponse(url=vNext or fHomePathFor(vUser), status_code=303)
  return cTemplates.TemplateResponse(
    request=pRequest,
    name="login.html",
    context={"vNext": vNext, "vRegistrationOpen": fGetSettingsStore().mIsRegistrationOpen()}
  )


@vAuthPagesRouter.get("/auth/register/", response_class=HTMLResponse)
def fRegisterPage(pRequest: Request):
  """Form to create an account (role user)"""
  vUser = fGetCurrentUser(pRequest)
  if vUser:
    return RedirectResponse(url=fHomePathFor(vUser), status_code=303)
  return cTemplates.TemplateResponse(
    request=pRequest,
    name="register.html",
    context={"vRegistrationOpen": fGetSettingsStore().mIsRegistrationOpen()}
  )


@vAuthPagesRouter.get("/auth/recover/", response_class=HTMLResponse)
def fRecoverPage(pRequest: Request):
  """Form to set a new password with the recovery code"""
  return cTemplates.TemplateResponse(request=pRequest, name="recover.html", context={})


@vAuthApiRouter.post("/login", summary="Start a dashboard session (sets the session cookie)")
def fApiLogin(pRequest: Request, pData: LoginSchema):
  vAddress = fClientAddress(pRequest)
  if fRecentFailures(vAddress) >= cMaxFailedLogins:
    raise HTTPException(status_code=429, detail={"error": {"message": "Too many failed attempts, try again later", "type": "too_many_attempts"}})

  vStore = fGetUserStore()
  vUser = vStore.mAuthenticate(pData.username.strip(), pData.password)
  if not vUser:
    fRememberFailure(vAddress)
    raise HTTPException(status_code=401, detail={"error": {"message": "Wrong username or password", "type": "invalid_credentials"}})

  fForgetFailures(vAddress)
  vToken = vStore.mCreateSession(vUser["id"])
  vRedirect = pData.next if fIsSafeNextPath(pData.next) else fHomePathFor(vUser)
  vResponse = JSONResponse(content={"ok": True, "redirect": vRedirect, "user": {"username": vUser["username"], "role": vUser["role"]}})
  fSetSessionCookie(vResponse, vToken)
  return vResponse


@vAuthApiRouter.post("/register", status_code=201, summary="Create an account with the role user, when the registration is open (sets the session cookie and returns the recovery code)")
def fApiRegister(pRequest: Request, pData: RegisterSchema):
  if not fGetSettingsStore().mIsRegistrationOpen():
    raise HTTPException(status_code=403, detail={"error": {"message": "The registration is closed", "type": "registration_closed"}})

  vAddress = fClientAddress(pRequest)
  if fRecentRegistrations(vAddress) >= cMaxRegistrations:
    raise HTTPException(status_code=429, detail={"error": {"message": "Too many accounts created from this address, try again later", "type": "too_many_registrations"}})

  vStore = fGetUserStore()
  try:
    vUser = vStore.mCreateUser(pData.username.strip(), pData.password, cRoleUser)
    vRecoveryCode = vStore.mNewRecoveryCode(vUser["username"])
  except UserError as vError:
    raise fUserErrorToHttp(vError)

  fRememberRegistration(vAddress)
  vToken = vStore.mCreateSession(vUser["id"])
  vResponse = JSONResponse(
    status_code=201,
    content={
      "ok": True,
      "redirect": fHomePathFor(vUser),
      "recovery_code": vRecoveryCode,
      "user": {"username": vUser["username"], "role": vUser["role"]}
    }
  )
  fSetSessionCookie(vResponse, vToken)
  return vResponse


@vAuthApiRouter.post("/recover", summary="Set a new password with the recovery code (it closes every session and returns a new code)")
def fApiRecover(pRequest: Request, pData: RecoverSchema):
  vAddress = fClientAddress(pRequest)
  if fRecentFailures(vAddress) >= cMaxFailedLogins:
    raise HTTPException(status_code=429, detail={"error": {"message": "Too many failed attempts, try again later", "type": "too_many_attempts"}})

  try:
    vNewCode = fGetUserStore().mRecoverPassword(pData.username.strip(), pData.recovery_code, pData.new_password)
  except UserError as vError:
    raise fUserErrorToHttp(vError)

  if not vNewCode:
    fRememberFailure(vAddress)
    raise HTTPException(status_code=400, detail={"error": {"message": "Wrong username or recovery code", "type": "invalid_recovery_code"}})

  fForgetFailures(vAddress)
  return {"ok": True, "redirect": "/auth/login/", "recovery_code": vNewCode}


@vAuthApiRouter.post("/logout", summary="Close the current dashboard session")
def fApiLogout(pRequest: Request):
  try:
    fGetUserStore().mDeleteSession(fGetSessionToken(pRequest))
  except Exception as vError:
    print(f"[AUTH] Error closing the session: {vError}")
  vResponse = JSONResponse(content={"ok": True, "redirect": "/auth/login/"})
  fClearSessionCookie(vResponse)
  return vResponse


@vAuthApiRouter.get("/session", summary="User of the current session")
def fApiSession(pRequest: Request):
  vUser = fRequireApiUser(pRequest)
  return {"username": vUser["username"], "role": vUser["role"], "created_at": vUser["created_at"]}
