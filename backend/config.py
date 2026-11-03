#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

import json
import os
import re
import sys
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator


# Application name (system user, home folder, database and service share it)
cAppName = "ainonyproxy"
cAppVersion = "0.4.0"

# Base folder of the installation. Everything the application stores lives here.
# AINONYPROXY_HOME only exists to run the code from a source checkout.
cHomeDir = Path(os.environ.get("AINONYPROXY_HOME", f"/opt/{cAppName}"))
cConfigDir = cHomeDir / "config"
cDbDir = cHomeDir / "db"
cCertificatesDir = cHomeDir / "certificates"
cLogsDir = cHomeDir / "logs"
cDefaultDbFile = cDbDir / f"{cAppName}.db"

# Code folders (backend/ and frontend/ live side by side inside webapp/)
cBackendDir = Path(__file__).resolve().parent
cFrontendDir = cBackendDir.parent / "frontend"
cDefaultConfigDir = cBackendDir / "config-defaults"

# Languages supported by spaCy
cSupportedLanguages = [
  "ca", "zh", "hr", "da", "nl", "en", "fi", "fr", "de", "el",
  "it", "ja", "ko", "lt", "mk", "nb", "pl", "pt", "ro", "ru",
  "sl", "es", "sv", "uk"
]

cLanguageCode = Literal[
  "ca", "zh", "hr", "da", "nl", "en", "fi", "fr", "de", "el",
  "it", "ja", "ko", "lt", "mk", "nb", "pl", "pt", "ro", "ru",
  "sl", "es", "sv", "uk"
]


# Supported API formats
cApiFormat = Literal["openai", "anthropic", "gemini"]


class ProviderConfig(BaseModel):
  """Configuration of an LLM provider"""
  url: str
  api_key: Optional[str] = None
  format: cApiFormat = "openai"
  model: Optional[str] = None  # Default model for this provider


class MaskingConfig(BaseModel):
  show_markers: bool = False
  marker_text: str = "[protected]"


class PiiDetectionConfig(BaseModel):
  presidio_url: str
  languages: list[cLanguageCode] = ["en"]
  fallback_language: cLanguageCode = "en"
  score_threshold: float = Field(default=0.7, ge=0, le=1)
  entities: list[str] = [
    "PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD",
    "IBAN_CODE", "IP_ADDRESS", "LOCATION"
  ]


class SslConfig(BaseModel):
  enabled: bool = False
  certfile: Optional[str] = None
  keyfile: Optional[str] = None

  @model_validator(mode='after')
  def mValidateCertificates(self):
    if self.enabled:
      if not self.certfile or not self.keyfile:
        raise ValueError("Enabled SSL requires 'certfile' and 'keyfile'")
    return self


class ServerConfig(BaseModel):
  port: int = Field(default=11080, ge=1, le=65535)
  ssl_port: int = Field(default=11443, ge=1, le=65535)
  host: str = "0.0.0.0"
  ssl: SslConfig = SslConfig()
  proxy_protocol: bool = False


class LoggingConfig(BaseModel):
  database: str = str(cDefaultDbFile)
  retention_days: int = Field(default=30, ge=0)
  log_content: bool = False
  log_masked_content: bool = True


class DashboardConfig(BaseModel):
  enabled: bool = True
  session_hours: int = Field(default=12, ge=1, le=720)


class UiConfig(BaseModel):
  default_language: str = "en-US"


class AppConfig(BaseModel):
  mode: Literal["mask"] = "mask"  # Only mask mode is supported with multiple providers
  server: ServerConfig = ServerConfig()
  providers: dict[str, ProviderConfig]  # Providers by name
  masking: MaskingConfig = MaskingConfig()
  pii_detection: PiiDetectionConfig
  logging: LoggingConfig = LoggingConfig()
  dashboard: DashboardConfig = DashboardConfig()
  ui: UiConfig = UiConfig()

  @model_validator(mode='after')
  def mValidateProviders(self):
    if not self.providers:
      raise ValueError("At least one provider is required in 'providers'")
    return self

  def mGetProvider(self, pName: str) -> Optional[ProviderConfig]:
    """Returns a provider by name"""
    return self.providers.get(pName)

  def mListProviders(self) -> list[str]:
    """Lists the names of the available providers"""
    return list(self.providers.keys())


def fIsLocalUrl(pUrl: str) -> bool:
  """Tells whether a URL points to a local service or to a private network"""
  try:
    vParsed = urlparse(pUrl)
    vHost = vParsed.hostname or ""
  except ValueError:
    return False
  if vHost in ("localhost", "127.0.0.1", "::1"):
    return True
  if vHost.startswith("10.") or vHost.startswith("192.168."):
    return True
  if vHost.startswith("172."):
    try:
      vSecondOctet = int(vHost.split(".")[1])
      if 16 <= vSecondOctet <= 31:
        return True
    except (IndexError, ValueError):
      pass
  return False


def fDetectFormat(pUrl: str, pExplicitFormat: Optional[str] = None) -> str:
  """Detects the API format from the URL, or uses the explicit one"""
  if pExplicitFormat:
    return pExplicitFormat
  if "anthropic.com" in pUrl:
    return "anthropic"
  if "generativelanguage.googleapis.com" in pUrl:
    return "gemini"
  return "openai"


def fReplaceEnvVars(pValue: str) -> str:
  """Replaces ${VAR} and ${VAR:-default} patterns with environment values"""
  def fReplace(pMatch):
    vExpression = pMatch.group(1)
    if ":-" in vExpression:
      vVarName, vDefaultValue = vExpression.split(":-", 1)
    else:
      vVarName = vExpression
      vDefaultValue = None

    vEnvValue = os.environ.get(vVarName)
    if vEnvValue:
      return vEnvValue
    if vDefaultValue is not None:
      return vDefaultValue
    print(f"Warning: the environment variable {vVarName} is not defined")
    return ""

  return re.sub(r'\$\{([^}]+)\}', fReplace, pValue)


def fReplaceEnvVarsInObject(pObject):
  """Replaces environment variables recursively inside an object"""
  if isinstance(pObject, str):
    return fReplaceEnvVars(pObject)
  if isinstance(pObject, list):
    return [fReplaceEnvVarsInObject(vItem) for vItem in pObject]
  if isinstance(pObject, dict):
    return {vKey: fReplaceEnvVarsInObject(vValue) for vKey, vValue in pObject.items()}
  return pObject


# Singleton configuration instance
_vConfigInstance: Optional[AppConfig] = None
_vCurrentConfigPath: Optional[str] = None


def fGetConfigDir() -> Path:
  """Returns the configuration folder"""
  global _vCurrentConfigPath
  if _vCurrentConfigPath:
    return Path(_vCurrentConfigPath).parent
  vConfigPath = os.environ.get("AINONYPROXY_CONFIG")
  if vConfigPath:
    return Path(vConfigPath).parent
  return cConfigDir


def fLoadApiUrls() -> dict:
  """Loads the provider URLs from config/api_urls.json"""
  vApiUrlsPath = fGetConfigDir() / "api_urls.json"

  if not vApiUrlsPath.exists():
    return {}

  try:
    vContent = vApiUrlsPath.read_text(encoding="utf-8")
    dApiUrls = json.loads(vContent)
    return fReplaceEnvVarsInObject(dApiUrls)
  except (json.JSONDecodeError, IOError) as vError:
    print(f"Error reading {vApiUrlsPath}: {vError}")
    return {}


def fLoadApiKeys() -> dict:
  """Loads the API keys from config/api_keys.json"""
  vApiKeysPath = fGetConfigDir() / "api_keys.json"

  if not vApiKeysPath.exists():
    return {}

  try:
    vContent = vApiKeysPath.read_text(encoding="utf-8")
    dApiKeys = json.loads(vContent)
    return fReplaceEnvVarsInObject(dApiKeys)
  except (json.JSONDecodeError, IOError) as vError:
    print(f"Warning: error reading {vApiKeysPath}: {vError}")
    return {}


def fSaveApiKeys(pApiKeys: dict) -> bool:
  """Saves the API keys in config/api_keys.json, readable only by its owner"""
  vApiKeysPath = fGetConfigDir() / "api_keys.json"

  try:
    vDescriptor = os.open(vApiKeysPath, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(vDescriptor, 'w', encoding='utf-8') as vFile:
      json.dump(pApiKeys, vFile, indent=2, ensure_ascii=False)
    os.chmod(vApiKeysPath, 0o600)
    return True
  except Exception as vError:
    print(f"Error saving {vApiKeysPath}: {vError}")
    return False


def fEnsureApiKeys():
  """Makes sure api_keys.json exists and has an entry for every provider.
  When keys are missing and there is a terminal, asks the user for them.
  Without a terminal (running as a service) it only adds empty entries."""
  dApiUrls = fLoadApiUrls()
  if not dApiUrls:
    return

  vApiKeysPath = fGetConfigDir() / "api_keys.json"
  vFileExists = vApiKeysPath.exists()
  dApiKeys = fLoadApiKeys()

  # Find providers without a key
  aMissing = []
  for vName in dApiUrls:
    if vName not in dApiKeys or not dApiKeys[vName]:
      aMissing.append(vName)

  if not aMissing:
    return

  vHasTerminal = False
  try:
    vHasTerminal = sys.stdin is not None and sys.stdin.isatty()
  except (AttributeError, ValueError):
    vHasTerminal = False

  if not vHasTerminal:
    # Running as a service: never block waiting for input
    if not vFileExists or any(vName not in dApiKeys for vName in dApiUrls):
      for vName in dApiUrls:
        if vName not in dApiKeys:
          dApiKeys[vName] = ""
      fSaveApiKeys(dApiKeys)
    print(f"[STARTUP] Providers without an API key: {', '.join(aMissing)} (edit {vApiKeysPath})")
    return

  if not vFileExists:
    print(f"\n[STARTUP] {vApiKeysPath} does not exist. Creating it...\n")
  else:
    print("\n[STARTUP] Some providers have no API key.\n")

  print("  Type the API key of each provider.")
  print("  (Press Enter to leave it empty if it does not need an API key)\n")

  for vName in aMissing:
    vUrl = dApiUrls[vName].get("url", "")
    try:
      vInput = input(f"  API key for {vName} ({vUrl}): ").strip()
    except EOFError:
      vInput = ""
    dApiKeys[vName] = vInput

  # Make sure every provider has an entry
  for vName in dApiUrls:
    if vName not in dApiKeys:
      dApiKeys[vName] = ""

  fSaveApiKeys(dApiKeys)
  print(f"\n[STARTUP] ✓ API keys saved in {vApiKeysPath}\n")


def fLoadPiiDetection() -> dict:
  """Loads the PII detection configuration from config/pii_detection.json"""
  vPiiPath = fGetConfigDir() / "pii_detection.json"

  if not vPiiPath.exists():
    return {}

  try:
    vContent = vPiiPath.read_text(encoding="utf-8")
    dPii = json.loads(vContent)
    return fReplaceEnvVarsInObject(dPii)
  except (json.JSONDecodeError, IOError) as vError:
    print(f"Error reading {vPiiPath}: {vError}")
    return {}


def fLoadConfig(pConfigPath: Optional[str] = None) -> AppConfig:
  """Loads the configuration from JSON, replacing environment variables"""
  global _vCurrentConfigPath

  vPath = pConfigPath or os.environ.get("AINONYPROXY_CONFIG")
  aPaths = [vPath] if vPath else [str(cConfigDir / "config.json")]

  vConfigFile = None
  vFoundPath = None
  for vCandidate in aPaths:
    if Path(vCandidate).exists():
      try:
        vConfigFile = Path(vCandidate).read_text(encoding="utf-8")
      except (IOError, UnicodeDecodeError) as vError:
        raise ValueError(f"Error reading the configuration file '{vCandidate}': {vError}")
      vFoundPath = vCandidate
      break

  if not vConfigFile:
    raise ValueError(
      f"No configuration file was found. Tried: {', '.join(aPaths)}\n"
      f"Copy the files of {cDefaultConfigDir} into {cConfigDir}"
    )

  _vCurrentConfigPath = vFoundPath

  try:
    dRawConfig = json.loads(vConfigFile)
  except json.JSONDecodeError as vError:
    raise ValueError(f"Error parsing the configuration JSON: {vError}")
  dConfigWithEnv = fReplaceEnvVarsInObject(dRawConfig)

  # Build the providers from api_urls.json + api_keys.json
  dApiUrls = fLoadApiUrls()
  dApiKeys = fLoadApiKeys()

  if dApiUrls:
    dProviders = {}
    for vName, dUrlConfig in dApiUrls.items():
      vUrl = dUrlConfig.get("url", "")
      vExplicitFormat = dUrlConfig.get("format")
      vFormat = fDetectFormat(vUrl, vExplicitFormat)
      dProvider = {
        "url": vUrl,
        "format": vFormat,
      }
      if "model" in dUrlConfig:
        dProvider["model"] = dUrlConfig["model"]
      if vName in dApiKeys and dApiKeys[vName]:
        dProvider["api_key"] = dApiKeys[vName]
      dProviders[vName] = dProvider
    dConfigWithEnv["providers"] = dProviders

  # Load the PII detection from config/pii_detection.json
  dPiiDetection = fLoadPiiDetection()
  if dPiiDetection:
    dConfigWithEnv["pii_detection"] = dPiiDetection

  try:
    return AppConfig(**dConfigWithEnv)
  except Exception as vError:
    print("Configuration validation errors:")
    print(f"  {vError}")
    raise ValueError("Invalid configuration") from vError


def fGetConfig() -> AppConfig:
  global _vConfigInstance
  if _vConfigInstance is None:
    _vConfigInstance = fLoadConfig()
  return _vConfigInstance


def fSaveConfig(pConfig: AppConfig, pConfigPath: Optional[str] = None) -> bool:
  """Saves the configuration in a JSON file"""
  global _vConfigInstance, _vCurrentConfigPath

  vPath = pConfigPath or _vCurrentConfigPath or os.environ.get("AINONYPROXY_CONFIG") or str(cConfigDir / "config.json")

  try:
    dConfig = pConfig.model_dump(exclude_none=False)

    # Providers are managed in api_urls.json and api_keys.json
    dConfig.pop("providers", None)
    # PII detection is managed in pii_detection.json
    dConfig.pop("pii_detection", None)

    with open(vPath, 'w', encoding='utf-8') as vFile:
      json.dump(dConfig, vFile, indent=2, ensure_ascii=False)

    _vConfigInstance = pConfig
    return True
  except Exception as vError:
    print(f"Error saving the configuration: {vError}")
    return False


def fReloadConfig() -> AppConfig:
  """Reloads the configuration from the file"""
  global _vConfigInstance
  _vConfigInstance = fLoadConfig()
  return _vConfigInstance
