#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
PII detector that uses an integrated Presidio.
It does not need a separate HTTP service.
"""

import time
from dataclasses import dataclass
from typing import Optional

from config import fGetConfig, cLanguageCode
from presidio.analyzer import fGetAnalyzer
from services.language_detector import fGetLanguageDetector, LanguageDetectionResult


@dataclass
class PiiEntity:
  entity_type: str
  start: int
  end: int
  score: float


@dataclass
class PiiDetectionResult:
  has_pii: bool
  entities_per_message: list[list[PiiEntity]]
  new_entities: list[PiiEntity]
  scan_time_ms: int
  language: cLanguageCode
  language_fallback: bool
  detected_language: Optional[str] = None


class PiiDetector:
  """PII detector that uses the integrated Presidio"""

  def __init__(self):
    vConfig = fGetConfig()
    self._vScoreThreshold = vConfig.pii_detection.score_threshold
    self._aEntityTypes = vConfig.pii_detection.entities
    self._dLanguageValidation: Optional[dict] = None
    self._vAnalyzer = fGetAnalyzer()

  def mDetectPii(self, pText: str, pLanguage: cLanguageCode) -> list[PiiEntity]:
    """
    Detects PII entities in the text using Presidio directly.

    Args:
      pText: Text to analyze
      pLanguage: Language code

    Returns:
      List of detected PII entities
    """
    try:
      aResults = self._vAnalyzer.mAnalyze(
        pText=pText,
        pLanguage=pLanguage,
        pEntities=self._aEntityTypes,
        pThreshold=self._vScoreThreshold
      )

      return [
        PiiEntity(
          entity_type=vResult.entity_type,
          start=vResult.start,
          end=vResult.end,
          score=vResult.score
        )
        for vResult in aResults
      ]
    except Exception as vError:
      print(f"Error detecting PII: {vError}")
      raise

  def mAnalyzeMessages(self, pMessages: list[dict]) -> PiiDetectionResult:
    """Analyzes chat messages looking for PII"""
    vStart = time.time()
    vConfig = fGetConfig()

    try:
      # Find the last user message
      vLastUserIndex = -1
      for vIndex in range(len(pMessages) - 1, -1, -1):
        if pMessages[vIndex].get("role") == "user":
          vLastUserIndex = vIndex
          break

      if vLastUserIndex == -1 or not pMessages[vLastUserIndex].get("content"):
        return PiiDetectionResult(
          has_pii=False,
          entities_per_message=[[] for _ in pMessages],
          new_entities=[],
          scan_time_ms=int((time.time() - vStart) * 1000),
          language=vConfig.pii_detection.fallback_language,
          language_fallback=False
        )

      vText = pMessages[vLastUserIndex]["content"]
      vLanguageResult = fGetLanguageDetector().mDetect(vText)
      aNewEntities = self.mDetectPii(vText, vLanguageResult.language)

      aEntitiesPerMessage = [
        aNewEntities if vIndex == vLastUserIndex else []
        for vIndex in range(len(pMessages))
      ]

      return PiiDetectionResult(
        has_pii=len(aNewEntities) > 0,
        entities_per_message=aEntitiesPerMessage,
        new_entities=aNewEntities,
        scan_time_ms=int((time.time() - vStart) * 1000),
        language=vLanguageResult.language,
        language_fallback=vLanguageResult.used_fallback,
        detected_language=vLanguageResult.detected_language
      )
    except Exception as vError:
      print(f"Error analyzing the messages: {vError}")
      raise

  def mAnalyzeAllMessages(
    self,
    pMessages: list[dict],
    pLanguageResult: LanguageDetectionResult
  ) -> PiiDetectionResult:
    """Analyzes every message (user and assistant) looking for PII"""
    vStart = time.time()

    try:
      aEntitiesPerMessage = []
      for vMessage in pMessages:
        vContent = vMessage.get("content", "")
        vRole = vMessage.get("role", "")
        if vContent and vRole in ("user", "assistant"):
          aEntities = self.mDetectPii(vContent, pLanguageResult.language)
          aEntitiesPerMessage.append(aEntities)
        else:
          aEntitiesPerMessage.append([])

      return PiiDetectionResult(
        has_pii=any(len(vEntities) > 0 for vEntities in aEntitiesPerMessage),
        entities_per_message=aEntitiesPerMessage,
        new_entities=[],
        scan_time_ms=int((time.time() - vStart) * 1000),
        language=pLanguageResult.language,
        language_fallback=pLanguageResult.used_fallback,
        detected_language=pLanguageResult.detected_language
      )
    except Exception as vError:
      print(f"Error analyzing all the messages: {vError}")
      raise

  def mCheckHealth(self) -> bool:
    """Checks that Presidio is working"""
    return self._vAnalyzer.mCheckHealth()

  def mWaitUntilReady(self, pMaxAttempts: int = 30, pDelayMs: int = 1000) -> bool:
    """
    Tries to initialize Presidio.
    With the direct integration it only initializes the engine.
    """
    import time as time_module

    for vAttempt in range(1, pMaxAttempts + 1):
      try:
        self._vAnalyzer.mInitialize()
        return True
      except Exception as vError:
        if vAttempt == 1:
          print("[STARTUP] Initializing Presidio", end="", flush=True)
        elif vAttempt % 5 == 0:
          print(".", end="", flush=True)
        time_module.sleep(pDelayMs / 1000)

    print()
    return False

  def mIsLanguageSupported(self, pLanguage: str) -> bool:
    """Tells whether a language really has its spaCy model installed"""
    try:
      import spacy

      # Full language -> model map (matches presidio/setup.py)
      dModels = {
        "ca": "ca_core_news_md",
        "zh": "zh_core_web_md",
        "hr": "hr_core_news_md",
        "da": "da_core_news_md",
        "nl": "nl_core_news_md",
        "en": "en_core_web_lg",
        "fi": "fi_core_news_md",
        "fr": "fr_core_news_md",
        "de": "de_core_news_lg",
        "el": "el_core_news_md",
        "it": "it_core_news_md",
        "ja": "ja_core_news_md",
        "ko": "ko_core_news_md",
        "lt": "lt_core_news_md",
        "mk": "mk_core_news_md",
        "nb": "nb_core_news_md",
        "pl": "pl_core_news_md",
        "pt": "pt_core_news_md",
        "ro": "ro_core_news_md",
        "ru": "ru_core_news_md",
        "sl": "sl_core_news_md",
        "es": "es_core_news_md",
        "sv": "sv_core_news_md",
        "uk": "uk_core_news_md",
      }

      vModel = dModels.get(pLanguage)
      if not vModel:
        return False

      spacy.load(vModel)
      return True
    except Exception:
      return False

  def mValidateLanguages(self, pLanguages: list[str]) -> dict:
    """Validates that the configured languages have their models installed"""
    aAvailable = []
    aMissing = []

    for vLanguage in pLanguages:
      if self.mIsLanguageSupported(vLanguage):
        aAvailable.append(vLanguage)
      else:
        aMissing.append(vLanguage)

    self._dLanguageValidation = {
      "available": aAvailable,
      "missing": aMissing
    }

    return self._dLanguageValidation

  def mGetLanguageValidation(self) -> Optional[dict]:
    return self._dLanguageValidation


# Singleton instance
_vDetectorInstance: Optional[PiiDetector] = None


def fGetPiiDetector() -> PiiDetector:
  global _vDetectorInstance
  if _vDetectorInstance is None:
    _vDetectorInstance = PiiDetector()
  return _vDetectorInstance
