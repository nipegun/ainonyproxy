#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import json
import re

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import cFrontendDir, fGetConfig
from services.auth import (
  cAdminDashboardPath,
  cUserDashboardPath,
  fGetCurrentUser,
  fHomePathFor,
  fIsAdmin,
  fLoginRedirect,
  fRequireApiAdmin
)
from services.logger import fGetLogger

vDashboardPagesRouter = APIRouter(include_in_schema=False)
vAdminApiRouter = APIRouter(tags=["admin"])
vLanguagesApiRouter = APIRouter(tags=["ui"])

# Languages folder
cLangDir = cFrontendDir / "lang"
cLanguageCodePattern = re.compile(r"^[a-z]{2}-[A-Z]{2}$")

# Templates
cTemplatesDir = cFrontendDir / "templates"
cTemplates = Jinja2Templates(directory=str(cTemplatesDir))

# Tabs of each dashboard. The first one is the one that opens by default.
aAdminTabs = ["overview", "users", "account", "help"]
aUserTabs = ["api", "account", "help"]


def fRenderDashboard(pRequest: Request, pUser: dict, pRole: str, pTab: str, pTabs: list[str]):
  vBasePath = cAdminDashboardPath if pRole == "admin" else cUserDashboardPath
  return cTemplates.TemplateResponse(
    request=pRequest,
    name="dashboard.html",
    context={
      "vRole": pRole,
      "vTab": pTab,
      "aTabs": pTabs,
      "vBasePath": vBasePath,
      "vUsername": pUser["username"],
      "vIsAdmin": fIsAdmin(pUser)
    }
  )


@vDashboardPagesRouter.get("/")
def fRoot(pRequest: Request):
  """The root sends every visitor to the place that corresponds to them"""
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    return RedirectResponse(url="/auth/login/", status_code=303)
  return RedirectResponse(url=fHomePathFor(vUser), status_code=303)


@vDashboardPagesRouter.get("/admin/dashboard/")
def fAdminDashboardRoot(pRequest: Request):
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    return fLoginRedirect(pRequest)
  if not fIsAdmin(vUser):
    return RedirectResponse(url=cUserDashboardPath, status_code=303)
  return RedirectResponse(url=f"{cAdminDashboardPath}{aAdminTabs[0]}/", status_code=307)


@vDashboardPagesRouter.get("/admin/dashboard/{pTab}/", response_class=HTMLResponse)
def fAdminDashboardTab(pRequest: Request, pTab: str):
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    return fLoginRedirect(pRequest)
  if not fIsAdmin(vUser):
    return RedirectResponse(url=cUserDashboardPath, status_code=303)
  if pTab not in aAdminTabs:
    raise HTTPException(status_code=404)
  return fRenderDashboard(pRequest, vUser, "admin", pTab, aAdminTabs)


@vDashboardPagesRouter.get("/user/dashboard/")
def fUserDashboardRoot(pRequest: Request):
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    return fLoginRedirect(pRequest)
  return RedirectResponse(url=f"{cUserDashboardPath}{aUserTabs[0]}/", status_code=307)


@vDashboardPagesRouter.get("/user/dashboard/{pTab}/", response_class=HTMLResponse)
def fUserDashboardTab(pRequest: Request, pTab: str):
  vUser = fGetCurrentUser(pRequest)
  if not vUser:
    return fLoginRedirect(pRequest)
  if pTab not in aUserTabs:
    raise HTTPException(status_code=404)
  return fRenderDashboard(pRequest, vUser, "user", pTab, aUserTabs)


@vAdminApiRouter.get("/logs", summary="Recent requests")
def fApiLogs(
  pRequest: Request,
  pLimit: int = Query(default=100, ge=1, le=1000, alias="limit"),
  pOffset: int = Query(default=0, ge=0, alias="offset")
):
  """Returns the recent logs"""
  fRequireApiAdmin(pRequest)

  vLogger = fGetLogger()
  aLogs = vLogger.mGetLogs(pLimit, pOffset)

  return {
    "logs": aLogs,
    "pagination": {
      "limit": pLimit,
      "offset": pOffset,
      "count": len(aLogs)
    }
  }


@vAdminApiRouter.get("/stats", summary="Statistics of the requests")
def fApiStats(pRequest: Request):
  """Returns the statistics"""
  fRequireApiAdmin(pRequest)

  vConfig = fGetConfig()
  vLogger = fGetLogger()
  vStats = vLogger.mGetStatistics()
  aEntityStats = vLogger.mGetEntityStatistics()

  return {
    "total_requests": vStats.total_requests,
    "pii_requests": vStats.pii_requests,
    "pii_percentage": vStats.pii_percentage,
    "upstream_requests": vStats.upstream_requests,
    "local_requests": vStats.local_requests,
    "avg_scan_time_ms": vStats.avg_scan_time_ms,
    "total_tokens": vStats.total_tokens,
    "requests_last_hour": vStats.requests_last_hour,
    "entity_breakdown": aEntityStats,
    "mode": vConfig.mode
  }


@vLanguagesApiRouter.get("/languages", summary="Available interface languages")
def fApiLanguages():
  """Returns the available languages"""
  vConfig = fGetConfig()
  aLanguages = []

  # Look for JSON files in the lang folder
  if cLangDir.exists():
    for vFile in cLangDir.glob("*.json"):
      try:
        with open(vFile, "r", encoding="utf-8") as vOpenFile:
          dData = json.load(vOpenFile)
          if "meta" in dData:
            aLanguages.append({
              "code": dData["meta"].get("code", vFile.stem),
              "name": dData["meta"].get("name", vFile.stem),
              "flag": dData["meta"].get("flag", "")
            })
      except Exception:
        pass

  # Alphabetical order by code
  aLanguages.sort(key=lambda pLanguage: pLanguage["code"])

  # Default language of the configuration
  vDefaultLanguage = "en-US"
  if hasattr(vConfig, "ui") and hasattr(vConfig.ui, "default_language"):
    vDefaultLanguage = vConfig.ui.default_language

  return {
    "languages": aLanguages,
    "default": vDefaultLanguage
  }


@vLanguagesApiRouter.get("/languages/{pLangCode}", summary="Texts of one interface language")
def fApiLanguageFile(pLangCode: str = Path(..., description="Language code, e.g. en-US")):
  """Returns a specific language file"""
  if not cLanguageCodePattern.match(pLangCode):
    raise HTTPException(status_code=404, detail="Language not found")

  vLangFile = cLangDir / f"{pLangCode}.json"

  if not vLangFile.exists():
    raise HTTPException(status_code=404, detail="Language not found")

  return FileResponse(vLangFile, media_type="application/json")
