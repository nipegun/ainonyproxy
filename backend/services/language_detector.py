#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

from dataclasses import dataclass
from typing import Optional

from langdetect import detect, detect_langs

from config import fGetConfig, cLanguageCode


@dataclass
class LanguageDetectionResult:
  language: cLanguageCode
  used_fallback: bool
  detected_language: Optional[str] = None
  confidence: Optional[float] = None


# Special case: "no" is detected as Norwegian, but Presidio expects "nb"
dIsoToPresidioExceptions: dict[str, cLanguageCode] = {
  "no": "nb",  # Norwegian (generic) → Norwegian Bokmål
}


class LanguageDetector:
  def __init__(self):
    vConfig = fGetConfig()
    self._aConfiguredLanguages: list[cLanguageCode] = vConfig.pii_detection.languages
    self._vFallbackLanguage: cLanguageCode = vConfig.pii_detection.fallback_language

  def mDetect(self, pText: str) -> LanguageDetectionResult:
    if len(self._aConfiguredLanguages) == 1:
      return LanguageDetectionResult(
        language=self._aConfiguredLanguages[0],
        used_fallback=False
      )

    try:
      vDetectedIso = detect(pText)
      aResults = detect_langs(pText)
      vConfidence = aResults[0].prob if aResults else 0

      # Use the exception when there is one
      vPresidioLanguage = dIsoToPresidioExceptions.get(vDetectedIso, vDetectedIso)

      if vPresidioLanguage in self._aConfiguredLanguages:
        return LanguageDetectionResult(
          language=vPresidioLanguage,
          used_fallback=False,
          detected_language=vDetectedIso,
          confidence=vConfidence
        )

      return LanguageDetectionResult(
        language=self._vFallbackLanguage,
        used_fallback=True,
        detected_language=vDetectedIso,
        confidence=vConfidence
      )
    except Exception:
      return LanguageDetectionResult(
        language=self._vFallbackLanguage,
        used_fallback=True
      )


# Singleton instance
_vDetectorInstance: Optional[LanguageDetector] = None


def fGetLanguageDetector() -> LanguageDetector:
  global _vDetectorInstance
  if _vDetectorInstance is None:
    _vDetectorInstance = LanguageDetector()
  return _vDetectorInstance
