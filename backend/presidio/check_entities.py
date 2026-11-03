#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Helper script: prints the entities Presidio supports for Spanish and English.

Usage:
  python3 presidio/check_entities.py
"""

import sys

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider


def fMain():
  try:
    vProvider = NlpEngineProvider(nlp_configuration={
      "nlp_engine_name": "spacy",
      "models": [
        {"lang_code": "es", "model_name": "es_core_news_md"},
        {"lang_code": "en", "model_name": "en_core_web_lg"}
      ]
    })
    vEngine = AnalyzerEngine(
      nlp_engine=vProvider.create_engine(),
      supported_languages=["es", "en"]
    )
    print("ES:", vEngine.get_supported_entities(language="es"))
    print("EN:", vEngine.get_supported_entities(language="en"))
  except Exception as vError:
    print(f"Error: {vError}")
    sys.exit(1)


if __name__ == "__main__":
  fMain()
