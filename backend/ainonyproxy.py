#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import argparse
import asyncio
import os
import secrets
import subprocess
import sys
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from config import (
  cAppName,
  cAppVersion,
  cCertificatesDir,
  fEnsureApiKeys,
  fGetConfig,
  fIsLocalUrl
)
from services.logger import fGetLogger
from services.port_guard import fFreePort
from services.settings import fGetSettingsStore
from services.users import cRoleAdmin, cRoles, UserError, fGetUserStore
from routes.auth import vAuthApiRouter, vAuthPagesRouter
from routes.chat import vChatRouter
from routes.dashboard import vAdminApiRouter, vDashboardPagesRouter, vLanguagesApiRouter
from routes.health import vHealthRouter
from routes.info import vInfoRouter
from routes.users import vAdminUsersRouter, vUserAccountRouter



# Global variables for the periodic tasks
_vCleanupTask = None

# Let's Encrypt certificates (they take priority) and the self-signed fallback
cLetsEncryptCertPath = cCertificatesDir / "fullchain.pem"
cLetsEncryptKeyPath = cCertificatesDir / "privkey.pem"
cSelfSignedCertPath = cCertificatesDir / "selfsigned-fullchain.pem"
cSelfSignedKeyPath = cCertificatesDir / "selfsigned-privkey.pem"


def fDetectCertificates():
  """Detects Let's Encrypt certificates in the certificates folder"""
  if cLetsEncryptCertPath.is_file() and cLetsEncryptKeyPath.is_file():
    return str(cLetsEncryptCertPath), str(cLetsEncryptKeyPath)
  return None, None


def fEnsureSelfSignedCertificate():
  """Returns a self-signed certificate, creating it with openssl when it does not exist"""
  if cSelfSignedCertPath.is_file() and cSelfSignedKeyPath.is_file():
    return str(cSelfSignedCertPath), str(cSelfSignedKeyPath)

  try:
    cCertificatesDir.mkdir(parents=True, exist_ok=True, mode=0o700)
    subprocess.run(
      [
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256",
        "-days", "3650",
        "-subj", f"/CN={cAppName}",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1",
        "-keyout", str(cSelfSignedKeyPath),
        "-out", str(cSelfSignedCertPath)
      ],
      check=True,
      capture_output=True,
      text=True
    )
    os.chmod(cSelfSignedKeyPath, 0o600)
    os.chmod(cSelfSignedCertPath, 0o644)
    print(f"[STARTUP] ✓ Self-signed certificate created in {cCertificatesDir}")
    return str(cSelfSignedCertPath), str(cSelfSignedKeyPath)
  except FileNotFoundError:
    print("[STARTUP] ✗ openssl is not installed: the self-signed certificate cannot be created")
  except subprocess.CalledProcessError as vError:
    print(f"[STARTUP] ✗ openssl could not create the self-signed certificate: {vError.stderr}")
  except OSError as vError:
    print(f"[STARTUP] ✗ The self-signed certificate could not be created: {vError}")
  return None, None


def fCreateRedirectApp(pSslPort):
  """Creates an ASGI app that permanently redirects all HTTP to HTTPS (308 keeps the method)"""
  vRedirectApp = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

  @vRedirectApp.middleware("http")
  async def fRedirectToHttps(pRequest: Request, pCallNext):
    vHost = pRequest.headers.get("host", "").split(":")[0]
    if pSslPort == 443:
      vHttpsUrl = f"https://{vHost}{pRequest.url.path}"
    else:
      vHttpsUrl = f"https://{vHost}:{pSslPort}{pRequest.url.path}"
    if pRequest.url.query:
      vHttpsUrl += f"?{pRequest.url.query}"
    return RedirectResponse(url=vHttpsUrl, status_code=308)

  return vRedirectApp


def fValidateApiKeys():
  """Validates that the remote providers have an API key configured"""
  vConfig = fGetConfig()

  aMissing = []
  for vName, vProviderConfig in vConfig.providers.items():
    if not fIsLocalUrl(vProviderConfig.url) and not vProviderConfig.api_key:
      aMissing.append(vName)

  if aMissing:
    print(f"[STARTUP] ⚠ Remote providers without an API key (they will not work): {', '.join(aMissing)}")
  else:
    print("[STARTUP] ✓ API keys validated")


def fValidateStartup():
  """Validates that Presidio is available and the configured languages too"""
  fValidateApiKeys()
  vConfig = fGetConfig()
  from services.pii_detector import fGetPiiDetector
  vDetector = fGetPiiDetector()

  # Initialize Presidio (integrated directly)
  print("[STARTUP] Initializing Presidio...")
  vReady = vDetector.mWaitUntilReady(30, 1000)

  if not vReady:
    print("[STARTUP] ✗ Presidio could not be initialized")
    print("          Make sure the dependencies are installed:")
    print("          pip install presidio-analyzer presidio-anonymizer spacy")
    sys.exit(1)

  print("[STARTUP] ✓ Presidio initialized")

  # Validate the configured languages
  print(f"[STARTUP] Validating languages: {', '.join(vConfig.pii_detection.languages)}")
  dValidation = vDetector.mValidateLanguages(vConfig.pii_detection.languages)

  if dValidation["missing"]:
    print("\n❌ Missing spaCy models!\n")
    print(f"   Configured: {', '.join(vConfig.pii_detection.languages)}")
    print(f"   Available:  {', '.join(dValidation['available']) if dValidation['available'] else '(none)'}")
    print(f"   Missing:    {', '.join(dValidation['missing'])}\n")
    print("   To install the missing models:")
    print(f"   python3 presidio/setup.py --languages {','.join(dValidation['missing'])}\n")
    print("[STARTUP] ✗ Missing language models. Exiting for safety.")
    sys.exit(1)
  else:
    print("[STARTUP] ✓ Every configured language is available")


def fEnsureAdminUser():
  """Without any user nobody could log in: the first start creates the administrator"""
  vStore = fGetUserStore()
  if vStore.mListUsers():
    return
  vPassword = secrets.token_urlsafe(15)
  vStore.mCreateUser("admin", vPassword, cRoleAdmin)
  print("")
  print("[STARTUP] ✓ There were no users. Administrator created:")
  print("          Username: admin")
  print(f"          Password: {vPassword}")
  print("          Change it in the 'Account' tab of the dashboard.")
  print("")


def fPrintStartupBanner(pConfig, pHost: str, pPort: int):
  """Prints the startup banner"""
  # Build the list of provider endpoints
  aEndpoints = []
  for vName, vProviderConfig in pConfig.providers.items():
    aEndpoints.append(f"  /api/ai/{vName} ({vProviderConfig.format})")

  vEndpointList = "\n".join(aEndpoints)

  vSslPort = pConfig.server.ssl_port

  vAccessBanner = f"""
  HTTPS:      https://{pHost}:{vSslPort}
  Login:      https://{pHost}:{vSslPort}/auth/login/
  Status:     https://{pHost}:{vSslPort}/api/ai/status
  Info:       https://{pHost}:{vSslPort}/api/ai/info
  Swagger:    https://{pHost}:{vSslPort}/api/doc/
  HTTP:       http://{pHost}:{pPort} (permanent redirect to HTTPS, 308)"""

  print(f"""
╔═══════════════════════════════════════════════════════════╗
║                        ainonyproxy                        ║
║              Smart LLM proxy with privacy                 ║
╚═══════════════════════════════════════════════════════════╝
{vAccessBanner}

Available endpoints:
{vEndpointList}

Mode:        {pConfig.mode.upper()}
Masking:
  Markers:   {'enabled' if pConfig.masking.show_markers else 'disabled'}

Detection:
  Languages: {', '.join(pConfig.pii_detection.languages)}
  Fallback:  {pConfig.pii_detection.fallback_language}
  Threshold: {pConfig.pii_detection.score_threshold}
  Entities:  {', '.join(pConfig.pii_detection.entities)}

SSL:         ENABLED (port {vSslPort}, certificate {pConfig.server.ssl.certfile})
PROXY proto: {'ENABLED' if pConfig.server.proxy_protocol else 'disabled'}
""")


async def fPeriodicCleanupTask(pConfig):
  """Runs the log cleanup periodically"""
  if pConfig.logging.retention_days <= 0:
    return

  vLogger = fGetLogger()

  # First cleanup
  try:
    vDeleted = vLogger.mCleanup()
    if vDeleted > 0:
      print(f"Log cleanup: {vDeleted} entries older than {pConfig.logging.retention_days} days")
  except Exception as vError:
    print(f"Log cleanup failed: {vError}")

  # Daily cleanup
  while True:
    await asyncio.sleep(24 * 60 * 60)  # 24 hours
    try:
      vCount = vLogger.mCleanup()
      if vCount > 0:
        print(f"Log cleanup: {vCount} entries older than {pConfig.logging.retention_days} days")
    except Exception as vError:
      print(f"Log cleanup failed: {vError}")


@asynccontextmanager
async def fLifespan(pApp: FastAPI):
  """Manages the life cycle of the application"""
  global _vCleanupTask

  vConfig = fGetConfig()

  # Startup validation (synchronous, integrated Presidio)
  fValidateStartup()

  # Users of the dashboards
  fEnsureAdminUser()

  # Print the banner
  fPrintStartupBanner(vConfig, vConfig.server.host, vConfig.server.port)

  # Start the log cleanup task
  _vCleanupTask = asyncio.create_task(fPeriodicCleanupTask(vConfig))

  yield

  # Shutdown
  print("\nShutting down...")
  if _vCleanupTask:
    _vCleanupTask.cancel()
    try:
      await _vCleanupTask
    except asyncio.CancelledError:
      pass

  try:
    fGetLogger().mClose()
  except Exception:
    pass

  try:
    fGetUserStore().mClose()
  except Exception:
    pass

  try:
    fGetSettingsStore().mClose()
  except Exception:
    pass


# Create the FastAPI application
vApp = FastAPI(
  title="ainonyproxy",
  description="Smart LLM proxy with privacy protection and multi-provider support",
  version=cAppVersion,
  lifespan=fLifespan,
  docs_url="/api/doc/",
  redoc_url="/api/doc/redoc/",
  openapi_url="/api/doc/openapi.json",
  swagger_ui_oauth2_redirect_url="/api/doc/oauth2-redirect"
)

# CORS middleware. Without credentials: another web site can call the AI API,
# but it can never use the dashboard session cookie of whoever visits it.
vApp.add_middleware(
  CORSMiddleware,
  allow_origins=["*"],
  allow_credentials=False,
  allow_methods=["*"],
  allow_headers=["*"]
)


# Request ID middleware and basic security headers
@vApp.middleware("http")
async def fRequestIdMiddleware(pRequest: Request, pCallNext):
  import uuid
  vRequestId = pRequest.headers.get("x-request-id") or str(uuid.uuid4())
  vResponse = await pCallNext(pRequest)
  vResponse.headers["X-Request-ID"] = vRequestId
  vResponse.headers.setdefault("X-Content-Type-Options", "nosniff")
  vResponse.headers.setdefault("X-Frame-Options", "DENY")
  vResponse.headers.setdefault("Referrer-Policy", "same-origin")
  return vResponse


# Register the routes
vApp.include_router(vHealthRouter, prefix="/api/ai")
vApp.include_router(vInfoRouter, prefix="/api/ai")
vApp.include_router(vChatRouter, prefix="/api/ai")
vApp.include_router(vAuthApiRouter, prefix="/api/auth")
vApp.include_router(vAdminApiRouter, prefix="/api/admin")
vApp.include_router(vAdminUsersRouter, prefix="/api/admin")
vApp.include_router(vUserAccountRouter, prefix="/api/user")
vApp.include_router(vLanguagesApiRouter, prefix="/api")
vApp.include_router(vAuthPagesRouter)
vApp.include_router(vDashboardPagesRouter)



# 404 error handler
@vApp.exception_handler(404)
async def fNotFoundHandler(pRequest: Request, pException):
  return JSONResponse(
    status_code=404,
    content={
      "error": {
        "message": f"Route not found: {pRequest.method} {pRequest.url.path}",
        "type": "not_found"
      }
    }
  )


# General error handler
@vApp.exception_handler(Exception)
async def fGeneralErrorHandler(pRequest: Request, pException):
  print(f"Unhandled error: {pException}")
  return JSONResponse(
    status_code=500,
    content={
      "error": {
        "message": "Internal server error",
        "type": "internal_error"
      }
    }
  )


def fRunCommandLine(pArgs) -> int:
  """User administration from the terminal. Returns the exit code."""
  vStore = fGetUserStore()

  if pArgs.user_exists:
    return 0 if vStore.mUserExists(pArgs.user_exists) else 1

  if pArgs.list_users:
    for dUser in vStore.mListUsers():
      print(f"{dUser['username']}\t{dUser['role']}\t{dUser['created_at']}")
    return 0

  if pArgs.set_user:
    if not pArgs.password_stdin:
      print("--set-user needs --password-stdin (the password is read from the standard input)")
      return 2
    vPassword = sys.stdin.readline().rstrip("\n")
    try:
      vResult = vStore.mSetUser(pArgs.set_user, vPassword, pArgs.role)
    except UserError as vError:
      print(f"Error: {vError}")
      return 2
    print(f"User '{pArgs.set_user}' {vResult} with the role '{pArgs.role}'")
    return 0

  return 2


def fParseArguments():
  vParser = argparse.ArgumentParser(description="ainonyproxy - Smart LLM proxy with privacy")
  vParser.add_argument("--user-exists", metavar="USERNAME", help="Exit code 0 when the user exists, 1 when it does not")
  vParser.add_argument("--list-users", action="store_true", help="List the dashboard users")
  vParser.add_argument("--set-user", metavar="USERNAME", help="Create the user, or change its password and role")
  vParser.add_argument("--role", choices=cRoles, default="user", help="Role for --set-user (default: user)")
  vParser.add_argument("--password-stdin", action="store_true", help="Read the password of --set-user from the standard input")
  return vParser.parse_args()


def fMain():
  """Main entry point"""
  vArgs = fParseArguments()
  if vArgs.user_exists or vArgs.list_users or vArgs.set_user:
    sys.exit(fRunCommandLine(vArgs))

  fEnsureApiKeys()
  vConfig = fGetConfig()
  vPort = vConfig.server.port
  vHost = vConfig.server.host
  vSslPort = vConfig.server.ssl_port

  # Auto-detect Let's Encrypt certificates
  vCertfile, vKeyfile = fDetectCertificates()

  if vCertfile is not None:
    print(f"[STARTUP] ✓ Let's Encrypt certificates detected in {cCertificatesDir}")
  elif vConfig.server.ssl.enabled:
    # Fallback to the certificates of the configuration
    vCertfile = vConfig.server.ssl.certfile
    vKeyfile = vConfig.server.ssl.keyfile
    print("[STARTUP] ✓ SSL enabled by configuration")
  else:
    # Without certificates the site is still served by HTTPS, with a self-signed one
    print(f"[STARTUP] No Let's Encrypt certificates in {cCertificatesDir}: using a self-signed certificate")
    vCertfile, vKeyfile = fEnsureSelfSignedCertificate()
    if vCertfile is None:
      print("[STARTUP] ✗ There is no certificate to serve HTTPS. Exiting.")
      sys.exit(1)

  # Update the config so the banner shows the real state
  vConfig.server.ssl.enabled = True
  vConfig.server.ssl.certfile = vCertfile
  vConfig.server.ssl.keyfile = vKeyfile

  # Close whatever is still listening on our ports before listening on them
  for vPortToFree in (vPort, vSslPort):
    if not fFreePort(vPortToFree):
      print(f"[STARTUP] ⚠ The port {vPortToFree} is still busy")

  # HTTP only redirects to HTTPS
  vRedirectApp = fCreateRedirectApp(vSslPort)

  if vConfig.server.proxy_protocol:
    # HTTPS with the PROXY protocol (for HAProxy send-proxy) through Hypercorn
    import signal
    from hypercorn.config import Config as HypercornConfig
    from hypercorn.asyncio import serve as fServeHypercorn

    vHttpsConfig = HypercornConfig()
    vHttpsConfig.bind = [f"{vHost}:{vSslPort}"]
    vHttpsConfig.certfile = vCertfile
    vHttpsConfig.keyfile = vKeyfile
    vHttpsConfig.proxy_protocol = True
    vHttpsConfig.loglevel = "info"
    vHttpsConfig.accesslog = "-"

    vHttpConfig = HypercornConfig()
    vHttpConfig.bind = [f"{vHost}:{vPort}"]
    vHttpConfig.loglevel = "info"
    vHttpConfig.accesslog = "-"

    vLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(vLoop)

    vShutdownEvent = asyncio.Event()
    for vSignal in (signal.SIGINT, signal.SIGTERM):
      vLoop.add_signal_handler(vSignal, vShutdownEvent.set)

    try:
      vLoop.run_until_complete(asyncio.gather(
        fServeHypercorn(vRedirectApp, vHttpConfig, shutdown_trigger=vShutdownEvent.wait),
        fServeHypercorn(vApp, vHttpsConfig, shutdown_trigger=vShutdownEvent.wait)
      ))
    finally:
      vLoop.close()

  else:
    vHttpConfig = uvicorn.Config(
      vRedirectApp,
      host=vHost,
      port=vPort,
      reload=False,
      log_level="info"
    )
    vHttpsConfig = uvicorn.Config(
      vApp,
      host=vHost,
      port=vSslPort,
      reload=False,
      log_level="info",
      ssl_keyfile=vKeyfile,
      ssl_certfile=vCertfile
    )

    vHttpServer = uvicorn.Server(vHttpConfig)
    vHttpsServer = uvicorn.Server(vHttpsConfig)

    vLoop = asyncio.new_event_loop()
    asyncio.set_event_loop(vLoop)
    try:
      vLoop.run_until_complete(asyncio.gather(
        vHttpServer.serve(),
        vHttpsServer.serve()
      ))
    finally:
      vLoop.close()


if __name__ == "__main__":
  try:
    fMain()
  except KeyboardInterrupt:
    sys.exit(130)
