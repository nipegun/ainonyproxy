#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from fastapi import APIRouter

from config import cAppVersion, fGetConfig
from services.decision import fGetRouter
from services.pii_detector import fGetPiiDetector

vInfoRouter = APIRouter(tags=["ai"])

cVersion = cAppVersion


@vInfoRouter.get("/info", summary="Metadata of the service")
async def fInfo():
  vConfig = fGetConfig()
  vRouter = fGetRouter()
  dProvidersInfo = vRouter.mGetProvidersInfo()
  vDetector = fGetPiiDetector()
  dLanguageValidation = vDetector.mGetLanguageValidation()

  dProviders = {}
  for vName, dInfo in dProvidersInfo["providers"].items():
    dProviders[vName] = {
      "name": vName,
      "intendpoint": f"/api/ai/{vName}",
      "extendpoint": dInfo.get("url", "")
    }

  dInfoResponse = {
    "name": "ainonyproxy",
    "version": cVersion,
    "description": "Smart LLM proxy with privacy - Multi-provider",
    "mode": vConfig.mode,
    "providers": dProviders,
    "detection": {
      "languages": (
        {
          "configured": list(vConfig.pii_detection.languages),
          "available": dLanguageValidation["available"],
          "missing": dLanguageValidation["missing"]
        }
        if dLanguageValidation
        else {"configured": list(vConfig.pii_detection.languages), "available": [], "missing": []}
      ),
      "fallback_language": vConfig.pii_detection.fallback_language,
      "score_threshold": vConfig.pii_detection.score_threshold,
      "entities": list(vConfig.pii_detection.entities)
    },
    "masking": {
      "show_markers": vConfig.masking.show_markers
    }
  }

  return dInfoResponse
