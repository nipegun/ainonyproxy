#!/usr/bin/env -S PYTHONDONTWRITEBYTECODE=1 python3

"""
Script that installs the spaCy models Presidio needs.

Usage:
  python3 presidio/setup.py --languages en,es
"""

import argparse
import subprocess
import sys


# Registry of spaCy languages and models
cLanguageRegistry = {
  "spacy_version": "3.8.0",
  "languages": {
    "ca": {"name": "Catalan", "model": "ca_core_news_md"},
    "zh": {"name": "Chinese", "model": "zh_core_web_md"},
    "hr": {"name": "Croatian", "model": "hr_core_news_md"},
    "da": {"name": "Danish", "model": "da_core_news_md"},
    "nl": {"name": "Dutch", "model": "nl_core_news_md"},
    "en": {"name": "English", "model": "en_core_web_lg"},
    "fi": {"name": "Finnish", "model": "fi_core_news_md"},
    "fr": {"name": "French", "model": "fr_core_news_md"},
    "de": {"name": "German", "model": "de_core_news_lg"},
    "el": {"name": "Greek", "model": "el_core_news_md"},
    "it": {"name": "Italian", "model": "it_core_news_md"},
    "ja": {"name": "Japanese", "model": "ja_core_news_md"},
    "ko": {"name": "Korean", "model": "ko_core_news_md"},
    "lt": {"name": "Lithuanian", "model": "lt_core_news_md"},
    "mk": {"name": "Macedonian", "model": "mk_core_news_md"},
    "nb": {"name": "Norwegian", "model": "nb_core_news_md"},
    "pl": {"name": "Polish", "model": "pl_core_news_md"},
    "pt": {"name": "Portuguese", "model": "pt_core_news_md"},
    "ro": {"name": "Romanian", "model": "ro_core_news_md"},
    "ru": {"name": "Russian", "model": "ru_core_news_md"},
    "sl": {"name": "Slovenian", "model": "sl_core_news_md"},
    "es": {"name": "Spanish", "model": "es_core_news_md"},
    "sv": {"name": "Swedish", "model": "sv_core_news_md"},
    "uk": {"name": "Ukrainian", "model": "uk_core_news_md"},
  }
}


def fInstallModel(pLanguage: str, pVersion: str) -> bool:
  """Installs the spaCy model of a language"""
  if pLanguage not in cLanguageRegistry["languages"]:
    print(f"  ✗ Unknown language: {pLanguage}")
    return False

  dConfig = cLanguageRegistry["languages"][pLanguage]
  vModel = dConfig["model"]
  vName = dConfig["name"]

  # 1) When it is already installed and loadable, do not reinstall it
  try:
    import spacy
    spacy.load(vModel)
    print(f"  ✓ {vModel} is already installed")
    return True
  except Exception:
    pass

  print(f"  Installing {vModel} ({vName})...")

  vUrl = (
    f"https://github.com/explosion/spacy-models/releases/download/"
    f"{vModel}-{pVersion}/{vModel}-{pVersion}-py3-none-any.whl"
  )

  try:
    # 2) Force pip with --break-system-packages on Debian (PEP 668)
    vResult = subprocess.run(
      [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--break-system-packages", vUrl],
      capture_output=True,
      text=True
    )

    if vResult.returncode == 0:
      print(f"  ✓ {vModel} installed")
      return True
    else:
      print(f"  ✗ Error installing {vModel}: {vResult.stderr}")
      return False
  except Exception as vError:
    print(f"  ✗ Error: {vError}")
    return False



def fMain():
  vParser = argparse.ArgumentParser(description="Install the spaCy models for Presidio")
  vParser.add_argument(
    "--languages",
    required=True,
    help="Comma separated list of languages (e.g. en,es,fr)"
  )
  vArgs = vParser.parse_args()

  aLanguages = [vLanguage.strip() for vLanguage in vArgs.languages.split(",") if vLanguage.strip()]

  if not aLanguages:
    print("Error: no languages were given")
    sys.exit(1)

  # Validate the languages
  aInvalidLanguages = [vLanguage for vLanguage in aLanguages if vLanguage not in cLanguageRegistry["languages"]]
  if aInvalidLanguages:
    print(f"Error: unknown languages: {', '.join(aInvalidLanguages)}")
    print(f"Available: {', '.join(sorted(cLanguageRegistry['languages'].keys()))}")
    sys.exit(1)

  print(f"\n==> Installing the spaCy models for: {', '.join(aLanguages)}\n")

  vVersion = cLanguageRegistry["spacy_version"]
  vSuccesses = 0
  vFailures = 0

  for vLanguage in aLanguages:
    if fInstallModel(vLanguage, vVersion):
      vSuccesses += 1
    else:
      vFailures += 1

  print(f"\n==> Result: {vSuccesses} installed, {vFailures} failed\n")

  if vFailures > 0:
    sys.exit(1)


if __name__ == "__main__":
  try:
    fMain()
  except KeyboardInterrupt:
    sys.exit(130)
