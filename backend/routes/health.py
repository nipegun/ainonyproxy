#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from services.decision import fGetRouter

vHealthRouter = APIRouter(tags=["ai"])


@vHealthRouter.get("/status", summary="Health of the proxy (200 online, 503 offline)")
def fStatus():
  try:
    vRouter = fGetRouter()
    dHealth = vRouter.mCheckHealth()
    vIsHealthy = dHealth["presidio"]
  except Exception as vError:
    print(f"[STATUS] Error checking the health: {vError}")
    vIsHealthy = False

  vStatusCode = 200 if vIsHealthy else 503

  return JSONResponse(
    content={
      "status": "online" if vIsHealthy else "offline"
    },
    status_code=vStatusCode
  )
