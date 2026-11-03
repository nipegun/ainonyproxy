#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from dataclasses import dataclass, field
from typing import Optional

from config import fGetConfig
from services.llm_client import LlmClient
from services.masking import fCreateMaskingContext, fMaskMessages, MaskingContext
from services.pii_detector import fGetPiiDetector, PiiDetectionResult
from services.language_detector import LanguageDetectionResult


@dataclass
class MaskDecision:
  """Masking decision for mask mode"""
  mode: str = "mask"
  provider: str = ""
  reason: str = ""
  pii_result: PiiDetectionResult = None
  masked_messages: list[dict] = field(default_factory=list)
  masking_context: MaskingContext = field(default_factory=fCreateMaskingContext)


class Router:
  """
  Router that decides how to handle the requests according to the PII detection.
  Supports several LLM providers at the same time.
  """

  def __init__(self):
    self._vConfig = fGetConfig()
    self._dClients: dict[str, LlmClient] = {}

    # Create one client for each configured provider
    for vName, vProviderConfig in self._vConfig.providers.items():
      self._dClients[vName] = LlmClient(
        vProviderConfig,
        vName,
        vProviderConfig.model
      )
      print(f"[ROUTER] Provider '{vName}' configured: {vProviderConfig.format} -> {vProviderConfig.url}")

  def mGetMode(self) -> str:
    """Returns the current mode"""
    return self._vConfig.mode

  def mProviderExists(self, pProviderName: str) -> bool:
    """Tells whether a provider exists"""
    return pProviderName in self._dClients

  def mListProviders(self) -> list[str]:
    """Lists the available providers"""
    return list(self._dClients.keys())

  async def mDecide(self, pMessages: list[dict], pProviderName: str) -> MaskDecision:
    """Decides how to handle the messages with PII detection and masking"""
    try:
      vDetector = fGetPiiDetector()
      vPiiResult = vDetector.mAnalyzeMessages(pMessages)

      return await self._mDecideMask(pMessages, vPiiResult, pProviderName)
    except Exception as vError:
      print(f"[ROUTER] Error deciding how to handle the request: {vError}")
      raise

  async def _mDecideMask(
    self,
    pMessages: list[dict],
    pPiiResult: PiiDetectionResult,
    pProviderName: str
  ) -> MaskDecision:
    """Mask mode: masks the PII before sending it to the provider"""
    if not pPiiResult.has_pii:
      return MaskDecision(
        mode="mask",
        provider=pProviderName,
        reason="No PII was detected",
        pii_result=pPiiResult,
        masked_messages=pMessages,
        masking_context=fCreateMaskingContext()
      )

    vDetector = fGetPiiDetector()
    vFullScan = vDetector.mAnalyzeAllMessages(
      pMessages,
      LanguageDetectionResult(
        language=pPiiResult.language,
        used_fallback=pPiiResult.language_fallback
      )
    )

    aMasked, vContext = fMaskMessages(pMessages, vFullScan.entities_per_message)
    aEntityTypes = list(set(vEntity.entity_type for vEntity in pPiiResult.new_entities))

    return MaskDecision(
      mode="mask",
      provider=pProviderName,
      reason=f"Masked PII: {', '.join(aEntityTypes)}",
      pii_result=pPiiResult,
      masked_messages=aMasked,
      masking_context=vContext
    )

  def mGetClient(self, pProviderName: str) -> LlmClient:
    """Returns the LLM client of a provider"""
    vClient = self._dClients.get(pProviderName)
    if not vClient:
      vAvailable = ", ".join(self._dClients.keys())
      raise ValueError(f"Provider '{pProviderName}' is not configured. Available: {vAvailable}")
    return vClient

  def mGetMaskingConfig(self):
    """Returns the masking configuration"""
    return self._vConfig.masking

  def mCheckHealth(self) -> dict:
    """Checks the health of the services"""
    try:
      vDetector = fGetPiiDetector()
      vPresidioHealth = vDetector.mCheckHealth()
    except Exception as vError:
      print(f"[ROUTER] Error checking the health of Presidio: {vError}")
      vPresidioHealth = False

    return {
      "presidio": vPresidioHealth,
      "providers": list(self._dClients.keys())
    }

  def mGetProvidersInfo(self) -> dict:
    """Returns the information of every provider"""
    dProviders = {}
    for vName, vClient in self._dClients.items():
      dProviders[vName] = vClient.mGetInfo()

    return {
      "mode": self._vConfig.mode,
      "providers": dProviders
    }


# Singleton instance
_vRouterInstance: Optional[Router] = None


def fGetRouter() -> Router:
  global _vRouterInstance
  if _vRouterInstance is None:
    _vRouterInstance = Router()
  return _vRouterInstance
