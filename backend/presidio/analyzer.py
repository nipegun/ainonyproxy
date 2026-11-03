#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Wrapper of the Presidio AnalyzerEngine for direct integration.
Removes the need for a separate HTTP service.
"""

from dataclasses import dataclass
from typing import Optional

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider


# Language -> spaCy model map
cSpacyModels = {
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


@dataclass
class DetectedEntity:
  """Detected PII entity"""
  entity_type: str
  start: int
  end: int
  score: float


class PiiAnalyzer:
  """
  PII analyzer that uses Presidio directly.
  Replaces the HTTP calls to a Presidio server.
  """

  def __init__(self):
    self._vEngine: Optional[AnalyzerEngine] = None
    self._aSupportedLanguages: list[str] = []

  def mInitialize(self):
    """Initializes the Presidio AnalyzerEngine with multi-language support"""
    if self._vEngine is not None:
      return

    from config import fGetConfig
    vConfig = fGetConfig()
    aLanguages = vConfig.pii_detection.languages

    print(f"[PRESIDIO] Initializing the AnalyzerEngine for the languages: {', '.join(aLanguages)}")

    # Build the model configuration for the configured languages
    aModels = []
    for vLanguage in aLanguages:
      vModel = cSpacyModels.get(vLanguage)
      if vModel:
        aModels.append({"lang_code": vLanguage, "model_name": vModel})
      else:
        print(f"[PRESIDIO] Warning: there is no model for the language '{vLanguage}'")

    if not aModels:
      raise ValueError("No spaCy models were found for the configured languages")

    # Create the NLP engine with multi-language support
    dConfiguration = {
      "nlp_engine_name": "spacy",
      "models": aModels
    }

    try:
      vProvider = NlpEngineProvider(nlp_configuration=dConfiguration)
      vNlpEngine = vProvider.create_engine()

      self._vEngine = AnalyzerEngine(
        nlp_engine=vNlpEngine,
        supported_languages=aLanguages
      )
      self._aSupportedLanguages = aLanguages
    except (OSError, ValueError, Exception) as vError:
      print(f"[PRESIDIO] Error creating the AnalyzerEngine: {vError}")
      raise

    print(f"[PRESIDIO] AnalyzerEngine ready with the languages: {', '.join(aLanguages)}")

  def mAnalyze(
    self,
    pText: str,
    pLanguage: str,
    pEntities: Optional[list[str]] = None,
    pThreshold: float = 0.0
  ) -> list[DetectedEntity]:
    """
    Analyzes a text looking for PII.

    Args:
      pText: Text to analyze
      pLanguage: Language code (e.g. 'en', 'es')
      pEntities: List of entity types to detect (optional)
      pThreshold: Minimum confidence threshold

    Returns:
      List of detected entities
    """
    if self._vEngine is None:
      self.mInitialize()

    try:
      aResults = self._vEngine.analyze(
        text=pText,
        language=pLanguage,
        entities=pEntities,
        score_threshold=pThreshold
      )

      return [
        DetectedEntity(
          entity_type=vResult.entity_type,
          start=vResult.start,
          end=vResult.end,
          score=vResult.score
        )
        for vResult in aResults
      ]
    except Exception as vError:
      print(f"[PRESIDIO] Error analyzing the text: {vError}")
      raise

  def mIsLanguageSupported(self, pLanguage: str) -> bool:
    """Tells whether a language has recognizers configured"""
    if self._vEngine is None:
      self.mInitialize()

    try:
      aEntities = self._vEngine.get_supported_entities(language=pLanguage)
      return len(aEntities) > 0
    except Exception:
      return False

  def mGetSupportedEntities(self, pLanguage: str) -> list[str]:
    """Returns the entities supported for a language"""
    if self._vEngine is None:
      self.mInitialize()

    try:
      return self._vEngine.get_supported_entities(language=pLanguage)
    except Exception:
      return []

  def mCheckHealth(self) -> bool:
    """Checks that Presidio is working"""
    try:
      if self._vEngine is None:
        self.mInitialize()
      # Simple analysis test
      self._vEngine.analyze(text="test", language="en", entities=["PERSON"])
      return True
    except Exception:
      return False


# Singleton instance
_vAnalyzerInstance: Optional[PiiAnalyzer] = None


def fGetAnalyzer() -> PiiAnalyzer:
  """Returns the singleton instance of the analyzer"""
  global _vAnalyzerInstance
  if _vAnalyzerInstance is None:
    _vAnalyzerInstance = PiiAnalyzer()
  return _vAnalyzerInstance
