#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel

from services.auth import fGetSessionToken, fRequireApiAdmin, fRequireApiUser
from services.settings import fGetSettingsStore
from services.users import UserError, cRoleUser, fGetUserStore

vAdminUsersRouter = APIRouter(tags=["admin"])
vUserAccountRouter = APIRouter(tags=["user"])


class NewUserSchema(BaseModel):
  username: str
  password: str
  role: str = cRoleUser


class PasswordResetSchema(BaseModel):
  password: str


class PasswordChangeSchema(BaseModel):
  current_password: str
  new_password: str


class RecoveryCodeSchema(BaseModel):
  current_password: str


class RegistrationSchema(BaseModel):
  open: bool


def fUserErrorToHttp(pError: UserError) -> HTTPException:
  vCode = str(pError)
  vStatus = 404 if vCode == "user_not_found" else 409 if vCode in ("user_exists", "last_admin") else 400
  return HTTPException(status_code=vStatus, detail={"error": {"message": vCode, "type": vCode}})


@vAdminUsersRouter.get("/users", summary="List the dashboard users")
def fApiListUsers(pRequest: Request):
  fRequireApiAdmin(pRequest)
  return {"users": fGetUserStore().mListUsers()}


@vAdminUsersRouter.post("/users", status_code=201, summary="Create a dashboard user (returns its recovery code, shown only once)")
def fApiCreateUser(pRequest: Request, pData: NewUserSchema):
  fRequireApiAdmin(pRequest)
  vStore = fGetUserStore()
  try:
    vUser = vStore.mCreateUser(pData.username.strip(), pData.password, pData.role)
    vRecoveryCode = vStore.mNewRecoveryCode(vUser["username"])
  except UserError as vError:
    raise fUserErrorToHttp(vError)
  return {"user": vStore.mGetUser(vUser["username"]), "recovery_code": vRecoveryCode}


@vAdminUsersRouter.delete("/users/{pUsername}", summary="Delete a dashboard user")
def fApiDeleteUser(pRequest: Request, pUsername: str = Path(..., description="User to delete")):
  vAdmin = fRequireApiAdmin(pRequest)
  if pUsername == vAdmin["username"]:
    raise HTTPException(status_code=409, detail={"error": {"message": "cannot_delete_self", "type": "cannot_delete_self"}})
  try:
    fGetUserStore().mDeleteUser(pUsername)
  except UserError as vError:
    raise fUserErrorToHttp(vError)
  return {"ok": True}


@vAdminUsersRouter.put("/users/{pUsername}/password", summary="Set a new password for a user")
def fApiResetPassword(pRequest: Request, pData: PasswordResetSchema, pUsername: str = Path(..., description="User whose password changes")):
  fRequireApiAdmin(pRequest)
  vStore = fGetUserStore()
  try:
    vStore.mSetPassword(pUsername, pData.password)
    vUser = vStore.mGetUser(pUsername)
    if vUser:
      # Whoever had that account open has to log in again
      vStore.mDeleteUserSessions(vUser["id"])
  except UserError as vError:
    raise fUserErrorToHttp(vError)
  return {"ok": True}


@vAdminUsersRouter.get("/registration", summary="Whether anybody can create an account at /auth/register/")
def fApiGetRegistration(pRequest: Request):
  fRequireApiAdmin(pRequest)
  return {"open": fGetSettingsStore().mIsRegistrationOpen()}


@vAdminUsersRouter.put("/registration", summary="Open or close the registration at /auth/register/")
def fApiSetRegistration(pRequest: Request, pData: RegistrationSchema):
  fRequireApiAdmin(pRequest)
  vSettings = fGetSettingsStore()
  vSettings.mSetRegistrationOpen(pData.open)
  return {"open": vSettings.mIsRegistrationOpen()}


@vUserAccountRouter.get("/account", summary="Account of the current user")
def fApiAccount(pRequest: Request):
  vUser = fRequireApiUser(pRequest)
  return {
    "username": vUser["username"],
    "role": vUser["role"],
    "created_at": vUser["created_at"],
    "has_recovery_code": vUser["has_recovery_code"],
    "recovery_code_created_at": vUser["recovery_code_created_at"]
  }


@vUserAccountRouter.post("/account/recovery-code", summary="Create a new recovery code for the current user (the previous one stops working)")
def fApiNewRecoveryCode(pRequest: Request, pData: RecoveryCodeSchema):
  vUser = fRequireApiUser(pRequest)
  vStore = fGetUserStore()
  if not vStore.mAuthenticate(vUser["username"], pData.current_password):
    raise HTTPException(status_code=400, detail={"error": {"message": "wrong_current_password", "type": "wrong_current_password"}})
  try:
    vRecoveryCode = vStore.mNewRecoveryCode(vUser["username"])
  except UserError as vError:
    raise fUserErrorToHttp(vError)
  vUpdated = vStore.mGetUser(vUser["username"]) or {}
  return {"recovery_code": vRecoveryCode, "recovery_code_created_at": vUpdated.get("recovery_code_created_at")}


@vUserAccountRouter.put("/account/password", summary="Change the password of the current user")
def fApiChangePassword(pRequest: Request, pData: PasswordChangeSchema):
  vUser = fRequireApiUser(pRequest)
  vStore = fGetUserStore()
  if not vStore.mAuthenticate(vUser["username"], pData.current_password):
    raise HTTPException(status_code=400, detail={"error": {"message": "wrong_current_password", "type": "wrong_current_password"}})
  try:
    vStore.mSetPassword(vUser["username"], pData.new_password)
    # The other open sessions of this account are closed; this one stays
    vStore.mDeleteUserSessions(vUser["id"], fGetSessionToken(pRequest))
  except UserError as vError:
    raise fUserErrorToHttp(vError)
  return {"ok": True}
