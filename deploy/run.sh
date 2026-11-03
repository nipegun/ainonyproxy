#!/bin/bash

set -euo pipefail

# ------------------------------------------------------------------------------
# ainonyproxy - manual launcher (without the service)
#
# Creates the virtual environment when it does not exist, installs what is
# missing (Python packages, default configuration, spaCy models) and starts
# ainonyproxy in the foreground.
#
# Everything is stored in $AINONYPROXY_HOME (by default /opt/ainonyproxy), so
# run it as root, or point AINONYPROXY_HOME to a folder you can write:
#   AINONYPROXY_HOME="$PWD/_/temp/home" deploy/run.sh
# ------------------------------------------------------------------------------

cProjectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cBackendDir="$cProjectDir/backend"
cHomeDir="${AINONYPROXY_HOME:-/opt/ainonyproxy}"
cVenvDir="$cHomeDir/venv"
cConfigDir="$cHomeDir/config"
cDefaultConfigDir="$cBackendDir/config-defaults"
cRequirementsFile="$cBackendDir/requirements.txt"
cConfigFile="$cConfigDir/config.json"
cPiiConfigFile="$cConfigDir/pii_detection.json"

fCleanup() {
  :
}

trap fCleanup EXIT

fCheckVenv() {
  # Check that the virtual environment exists with its Python interpreter
  if [[ ! -f "$cVenvDir/bin/python3" ]]; then
    return 1
  fi
  return 0
}

fCheckPackages() {
  # Check that every package of requirements.txt is installed
  if "$cVenvDir/bin/pip" install --dry-run -r "$cRequirementsFile" 2>&1 | grep -q "Would install"; then
    return 1
  fi
  return 0
}

fInstallDefaultConfig() {
  # Copy the default configuration files that do not exist yet
  local vDefaultFile
  local vTargetFile
  mkdir -p "$cConfigDir"
  chmod 700 "$cConfigDir"
  for vDefaultFile in "$cDefaultConfigDir/"*.json; do
    vTargetFile="$cConfigDir/$(basename "$vDefaultFile")"
    if [[ ! -f "$vTargetFile" ]]; then
      cp "$vDefaultFile" "$vTargetFile"
      chmod 600 "$vTargetFile"
      echo "  Default configuration installed: $vTargetFile"
    fi
  done
}

fGetLanguages() {
  # Read the configured languages from pii_detection.json
  "$cVenvDir/bin/python3" -c '
import json, sys
try:
  with open(sys.argv[1], "r", encoding="utf-8") as vFile:
    dConfig = json.load(vFile)
  for vLanguage in dConfig.get("languages", []):
    print(vLanguage)
except Exception:
  print("es")
  print("en")
' "$cPiiConfigFile"
}

fCheckSpacyModels() {
  # Check that the spaCy models of the configured languages are installed
  local vModelsMap
  local vLanguage
  local vModel
  local vMissing=0
  vModelsMap='{"ca":"ca_core_news_md","zh":"zh_core_web_md","hr":"hr_core_news_md","da":"da_core_news_md","nl":"nl_core_news_md","en":"en_core_web_lg","fi":"fi_core_news_md","fr":"fr_core_news_md","de":"de_core_news_lg","el":"el_core_news_md","it":"it_core_news_md","ja":"ja_core_news_md","ko":"ko_core_news_md","lt":"lt_core_news_md","mk":"mk_core_news_md","nb":"nb_core_news_md","pl":"pl_core_news_md","pt":"pt_core_news_md","ro":"ro_core_news_md","ru":"ru_core_news_md","sl":"sl_core_news_md","es":"es_core_news_md","sv":"sv_core_news_md","uk":"uk_core_news_md"}'

  while IFS= read -r vLanguage; do
    vModel="$("$cVenvDir/bin/python3" -c 'import json, sys; print(json.loads(sys.argv[1]).get(sys.argv[2], ""))' "$vModelsMap" "$vLanguage")"
    if [[ -z "$vModel" ]]; then
      continue
    fi
    if ! "$cVenvDir/bin/python3" -c 'import spacy, sys; spacy.load(sys.argv[1])' "$vModel" 2> /dev/null; then
      vMissing=1
      break
    fi
  done < <(fGetLanguages)

  return "$vMissing"
}

fInstallSpacyModels() {
  local vLanguage
  echo "  Installing the spaCy models..."
  while IFS= read -r vLanguage; do
    "$cVenvDir/bin/python3" "$cBackendDir/presidio/setup.py" --languages "$vLanguage"
  done < <(fGetLanguages)
  echo ""
}

fRunSteps() {

  cd "$cBackendDir"

  if ! mkdir -p "$cHomeDir" 2> /dev/null || [[ ! -w "$cHomeDir" ]]; then
    echo ""
    echo "  $cHomeDir cannot be written. Run it as root or set AINONYPROXY_HOME."
    echo ""
    return 1
  fi

  # Check whether the virtual environment exists
    if ! fCheckVenv; then
      echo ""
      echo "  Virtual environment not found. Creating it..."
      echo ""
      python3 -m venv "$cVenvDir"
      "$cVenvDir/bin/python3" -m ensurepip --upgrade
    fi

  # Check whether packages are missing
    if ! fCheckPackages; then
      echo "  Installing the Python dependencies..."
      "$cVenvDir/bin/pip" install -r "$cRequirementsFile"
      echo ""
    fi

  # Check whether configuration files are missing
    fInstallDefaultConfig

  # Check whether spaCy models are missing
    if ! fCheckSpacyModels; then
      fInstallSpacyModels
    fi

  # Run ainonyproxy
    export AINONYPROXY_HOME="$cHomeDir"
    export AINONYPROXY_CONFIG="$cConfigFile"
    export PYTHONDONTWRITEBYTECODE=1
    exec "$cVenvDir/bin/python3" "$cBackendDir/ainonyproxy.py"

}

fMain() {
  local -a aFunctionNames
  local vExitCode=0
  # A function called inside `if !` runs with `set -e` suspended: the steps run
  # in a new bash, where it works again
  mapfile -t aFunctionNames < <(compgen -A function)
  export -f "${aFunctionNames[@]}"
  export cProjectDir cBackendDir cHomeDir cVenvDir cConfigDir cDefaultConfigDir cRequirementsFile cConfigFile cPiiConfigFile
  "$BASH" -c 'set -euo pipefail; fRunSteps' "$0" || vExitCode=$?
  # 130 is Ctrl+C: stopping it by hand is not an error
  if [[ "$vExitCode" -eq 130 ]]; then
    return 0
  fi
  return "$vExitCode"
}

if ! fMain; then
  echo ""
  echo "  Error running ainonyproxy."
  echo ""
fi
