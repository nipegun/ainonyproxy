#!/bin/bash

set -euo pipefail

# Piped to sh (BusyBox ash) instead of bash: say it clearly and stop.
# Plain POSIX shell, so that it runs before anything only bash understands.
if [ -z "${BASH_VERSION:-}" ]; then
  echo "This installer needs bash. Install bash and curl, and pipe it to bash, not to sh:" >&2
  echo "  apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install" >&2
  exit 1
fi

# ------------------------------------------------------------------------------
# ainonyproxy - Alpine Linux installer
#
# Usage (as root):
#   ./install-update-reinstall-alpine.sh [--install]         Install it (or update it when it is already installed)
#   ./install-update-reinstall-alpine.sh --update            Update code and dependencies, keeping config and data
#   ./install-update-reinstall-alpine.sh --reinstall [--yes] Delete the installation (not the certificates) and install it again
#
# From the network:
#   apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install
#
# It is idempotent: running it twice with the same option leaves the system in
# the same state. Everything it does is written to /root/webapp-install.log and
# the passwords it creates to /root/webapp-credentials.txt (both with mode 600).
#
# A fresh Alpine has no bash: install it first (apk add bash), as the line above
# does. The service is an OpenRC script in /etc/init.d/ainonyproxy.
#
# Piped from curl:
#   - Bash runs a piped script while it is still arriving. Here the top level
#     only defines constants and functions, and the last line runs them all, so
#     a download cut halfway runs nothing at all.
#   - The standard input of bash is the script itself. Every step runs with its
#     standard input on /dev/null, so no command can swallow the rest of the
#     script, and the only question (--reinstall without --yes) reads /dev/tty.
#   - A piped script has no repository around it, so the code is downloaded
#     from GitHub (cSourceTarballUrl). Run from a copy of the repository, it
#     uses the code of that copy.
#
# About `if ! fMain`: a function called as the condition of an `if` runs with
# `set -e` suspended, and so does everything it calls (even a background
# child). fMain therefore runs the real steps in a new bash process, which does
# get `set -e` back, so the first command that fails stops the installation.
# ------------------------------------------------------------------------------

# Constants
cAppName="ainonyproxy"
cAppUser="ainonyproxy"
cAppGroup="ainonyproxy"
cHomeDir="/opt/ainonyproxy"
cWebAppDir="/opt/ainonyproxy/webapp"
cVenvDir="/opt/ainonyproxy/venv"
cConfigDir="/opt/ainonyproxy/config"
cDbDir="/opt/ainonyproxy/db"
cCertificatesDir="/opt/ainonyproxy/certificates"
cLogsDir="/opt/ainonyproxy/logs"
cRunDir="/opt/ainonyproxy/run"
cInstallLogFile="/root/webapp-install.log"
cCredentialsFile="/root/webapp-credentials.txt"
cServiceFile="/etc/init.d/ainonyproxy"
cSourceTarballUrl="https://github.com/nipegun/ainonyproxy/archive/refs/heads/main.tar.gz"
cMinimumPythonVersion="3.13"
cAdminUser="admin"
cHttpPort="11080"
cHttpsPort="11443"
cVerifyAttempts="90"
cVerifySleepSeconds="2"

# Variables
vMode="install"
vAssumeYes="no"
vTempDir=""
vSourceDir=""
vTeePid=""
# Empty when the script arrives through a pipe (curl ... | bash)
vScriptPath="${BASH_SOURCE[0]:-}"

export PYTHONDONTWRITEBYTECODE=1

fCleanup() {
  local vAttempt
  # Remove the downloaded source code
  if [[ -n "${vTempDir:-}" && -d "$vTempDir" ]]; then
    rm -rf "$vTempDir"
  fi
  # Close the pipe to tee and give it a moment to write the last lines, so
  # that with `curl ... | bash` they do not appear after the prompt
  if [[ -n "${vTeePid:-}" ]]; then
    exec > /dev/null 2>&1
    for vAttempt in $(seq 1 50); do
      if ! kill -0 "$vTeePid" 2> /dev/null; then
        break
      fi
      sleep 0.1
    done
  fi
}

trap fCleanup EXIT

fNowStorage() {
  # Current moment in UTC, with the format of the rules: 2026-10-29@13-59-59.723
  local vNow
  vNow="$(date -u +'%Y-%m-%d@%H-%M-%S.%3N' 2>/dev/null || true)"
  if [[ ! "$vNow" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}@[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]{3}$ ]]; then
    vNow="$(date -u +'%Y-%m-%d@%H-%M-%S').000"
  fi
  printf '%s' "$vNow"
}

fLog() {
  printf '%s %s\n' "$(fNowStorage)" "$*"
}

fDie() {
  fLog "ERROR: $*"
  exit 1
}

fStartLogging() {
  # From here on, everything the script and its commands print also goes to the log
  touch "$cInstallLogFile"
  chmod 600 "$cInstallLogFile"
  exec > >(tee -a "$cInstallLogFile") 2>&1
  vTeePid="$!"
}

fShowHelp() {
  printf '%s\n' \
    "Usage: install-update-reinstall-alpine.sh [--install | --update | --reinstall] [--yes]" \
    "" \
    "  --install    Install ainonyproxy (the default). On an existing installation it updates it." \
    "  --update     Update the code and the dependencies. Configuration, database and certificates are kept." \
    "  --reinstall  Delete the installation (except the certificates) and install it again from zero." \
    "  --yes        Do not ask for confirmation in --reinstall." \
    "  --help       Show this help."
}

fParseArguments() {
  local vArgument
  for vArgument in "$@"; do
    case "$vArgument" in
      --install) vMode="install" ;;
      --update) vMode="update" ;;
      --reinstall) vMode="reinstall" ;;
      --yes|-y) vAssumeYes="yes" ;;
      --help|-h)
        fShowHelp
        exit 0
        ;;
      *) fDie "Unknown option: $vArgument (use --help)" ;;
    esac
  done
}

fCheckRoot() {
  if [[ "$(id -u)" -ne 0 ]]; then
    fDie "It must be run as root."
  fi
}

fCheckDistro() {
  if [[ ! -f /etc/alpine-release ]]; then
    fDie "This installer is for Alpine Linux. For Debian use install-update-reinstall-debian.sh."
  fi
}

fHasOpenRc() {
  command -v openrc-run > /dev/null 2>&1 && command -v rc-service > /dev/null 2>&1
}

fPrepareOpenRc() {
  # In a container OpenRC did not boot the system: it needs its softlevel file to run services
  if fHasOpenRc && [[ ! -f /run/openrc/softlevel ]]; then
    mkdir -p /run/openrc
    touch /run/openrc/softlevel
  fi
}

fHasTty() {
  ( : < /dev/tty ) 2>/dev/null
}

fConfirmReinstall() {
  local vAnswer=""
  if [[ "$vAssumeYes" == "yes" ]]; then
    return 0
  fi
  if ! fHasTty; then
    fDie "--reinstall deletes the configuration, the users and the logs. Without a terminal, run it again adding --yes."
  fi
  fLog "--reinstall will delete $cWebAppDir, $cVenvDir, $cConfigDir, $cDbDir and $cLogsDir (the certificates are kept)."
  printf '%s' "Type 'yes' to continue: " > /dev/tty
  read -r vAnswer < /dev/tty
  if [[ "$vAnswer" != "yes" ]]; then
    fDie "Reinstallation cancelled."
  fi
}

fInstallDependencies() {
  fLog "Installing the system dependencies"
  apk update
  apk add --no-cache \
    bash python3 py3-pip python3-dev build-base linux-headers \
    openssl curl ca-certificates tar coreutils openrc
}

fCheckPythonVersion() {
  if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)'; then
    fDie "Python $cMinimumPythonVersion or later is needed and this system has $(python3 -V 2>&1). Use an Alpine release whose python3 package is $cMinimumPythonVersion or later."
  fi
  fLog "$(python3 -V 2>&1) found"
}

fCreateAppUser() {
  if ! grep -q "^$cAppGroup:" /etc/group; then
    fLog "Creating the system group $cAppGroup"
    addgroup -S "$cAppGroup"
  fi
  if ! id -u "$cAppUser" > /dev/null 2>&1; then
    fLog "Creating the system user $cAppUser (home $cHomeDir, no login shell)"
    adduser -S -D -H -h "$cHomeDir" -s /sbin/nologin -G "$cAppGroup" "$cAppUser"
  fi
}

fCreateDirectories() {
  mkdir -p "$cHomeDir" "$cWebAppDir" "$cConfigDir" "$cDbDir" "$cCertificatesDir" "$cLogsDir" "$cRunDir"
}

fObtainSourceCode() {
  local vCandidate=""
  # Run from a copy of the repository: use that code
  if [[ -n "$vScriptPath" && -f "$vScriptPath" ]]; then
    vCandidate="$(cd "$(dirname "$vScriptPath")/.." && pwd)"
    if [[ -f "$vCandidate/backend/ainonyproxy.py" && -d "$vCandidate/frontend" ]]; then
      vSourceDir="$vCandidate"
      fLog "Using the source code of $vSourceDir"
      return 0
    fi
  fi
  # Piped from the network (curl ... | bash): download it
  fLog "Downloading the source code from $cSourceTarballUrl"
  if ! curl -fsSL --retry 3 --retry-delay 2 "$cSourceTarballUrl" -o "$vTempDir/source.tar.gz"; then
    fDie "The source code could not be downloaded from $cSourceTarballUrl"
  fi
  mkdir -p "$vTempDir/source"
  tar -xzf "$vTempDir/source.tar.gz" -C "$vTempDir/source" --strip-components=1
  vSourceDir="$vTempDir/source"
  if [[ ! -f "$vSourceDir/backend/ainonyproxy.py" ]]; then
    fDie "The downloaded code does not contain backend/ainonyproxy.py"
  fi
}

fStopManualProcess() {
  local vPid=""
  local vAttempt
  if [[ ! -f "$cRunDir/$cAppName.pid" ]]; then
    return 0
  fi
  vPid="$(cat "$cRunDir/$cAppName.pid")"
  if [[ "$vPid" =~ ^[0-9]+$ ]] && kill -0 "$vPid" 2> /dev/null; then
    fLog "Stopping the ainonyproxy process $vPid"
    kill "$vPid" 2> /dev/null || true
    for vAttempt in $(seq 1 20); do
      if ! kill -0 "$vPid" 2> /dev/null; then
        break
      fi
      sleep 0.5
    done
    if kill -0 "$vPid" 2> /dev/null; then
      kill -9 "$vPid" 2> /dev/null || true
    fi
  fi
  rm -f "$cRunDir/$cAppName.pid"
}

fStopService() {
  if fHasOpenRc && [[ -f "$cServiceFile" ]]; then
    fPrepareOpenRc
    if rc-service "$cAppName" status > /dev/null 2>&1; then
      fLog "Stopping the $cAppName service"
      rc-service "$cAppName" stop
    fi
  fi
  fStopManualProcess
}

fRemoveInstallation() {
  fLog "Removing the previous installation (the certificates are kept)"
  if fHasOpenRc && [[ -f "$cServiceFile" ]]; then
    rc-update del "$cAppName" default > /dev/null 2>&1 || true
  fi
  rm -f "$cServiceFile"
  rm -rf "$cWebAppDir" "$cVenvDir" "$cConfigDir" "$cDbDir" "$cLogsDir" "$cRunDir"
}

fDeploySourceCode() {
  fLog "Copying the code to $cWebAppDir"
  rm -rf "$cWebAppDir"
  mkdir -p "$cWebAppDir"
  cp -a "$vSourceDir/backend" "$cWebAppDir/backend"
  cp -a "$vSourceDir/frontend" "$cWebAppDir/frontend"
  find "$cWebAppDir" -type d -name '__pycache__' -prune -exec rm -rf {} +
}

fInstallDefaultConfig() {
  local vDefaultFile
  local vTargetFile
  # Only the files that do not exist yet: the configuration of the user is never overwritten
  for vDefaultFile in "$cWebAppDir/backend/config-defaults/"*.json; do
    vTargetFile="$cConfigDir/$(basename "$vDefaultFile")"
    if [[ ! -f "$vTargetFile" ]]; then
      cp "$vDefaultFile" "$vTargetFile"
      fLog "Default configuration installed: $vTargetFile"
    fi
  done
}

fBuildVirtualEnv() {
  # A virtual environment made with an older (or removed) Python is rebuilt
  if [[ -x "$cVenvDir/bin/python3" ]] && ! "$cVenvDir/bin/python3" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)' 2> /dev/null; then
    fLog "The virtual environment does not work with the current Python: rebuilding it"
    rm -rf "$cVenvDir"
  fi
  if [[ ! -x "$cVenvDir/bin/python3" ]]; then
    fLog "Creating the virtual environment in $cVenvDir"
    python3 -m venv "$cVenvDir"
  fi
  fLog "Installing the Python dependencies"
  "$cVenvDir/bin/python3" -m pip install --upgrade pip
  "$cVenvDir/bin/python3" -m pip install -r "$cWebAppDir/backend/requirements.txt"
}

fInstallSpacyModels() {
  local vLanguages
  vLanguages="$("$cVenvDir/bin/python3" -c 'import json, sys; print(",".join(json.load(open(sys.argv[1], encoding="utf-8")).get("languages", ["en"])))' "$cConfigDir/pii_detection.json")"
  fLog "Installing the spaCy models for: $vLanguages"
  "$cVenvDir/bin/python3" "$cWebAppDir/backend/presidio/setup.py" --languages "$vLanguages"
}

fGenerateCertificates() {
  local vHostname
  if [[ -f "$cCertificatesDir/fullchain.pem" && -f "$cCertificatesDir/privkey.pem" ]]; then
    fLog "Let's Encrypt certificates found in $cCertificatesDir"
    return 0
  fi
  if [[ -f "$cCertificatesDir/selfsigned-fullchain.pem" && -f "$cCertificatesDir/selfsigned-privkey.pem" ]]; then
    fLog "The self-signed certificate already exists"
    return 0
  fi
  vHostname="$(hostname 2> /dev/null || printf 'localhost')"
  fLog "There are no Let's Encrypt certificates: creating a self-signed certificate"
  openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
    -subj "/CN=$cAppName" \
    -addext "subjectAltName=DNS:localhost,DNS:$vHostname,IP:127.0.0.1,IP:::1" \
    -keyout "$cCertificatesDir/selfsigned-privkey.pem" \
    -out "$cCertificatesDir/selfsigned-fullchain.pem"
}

fSetPermissions() {
  # Everything under the home belongs to the application user; secrets only to it
  chown -R "$cAppUser:$cAppGroup" "$cHomeDir"
  chmod 750 "$cHomeDir"
  chmod 700 "$cConfigDir" "$cDbDir" "$cCertificatesDir"
  chmod 750 "$cLogsDir" "$cRunDir"
  find "$cConfigDir" "$cDbDir" -type f -exec chmod 600 {} +
  find "$cCertificatesDir" -type f -name '*privkey*' -exec chmod 600 {} +
}

fRunApp() {
  AINONYPROXY_HOME="$cHomeDir" "$cVenvDir/bin/python3" "$cWebAppDir/backend/ainonyproxy.py" "$@"
}

fGeneratePassword() {
  openssl rand -base64 32 | tr -dc 'A-Za-z0-9' | cut -c1-20
}

fWriteCredentialsFile() {
  local pPassword="$1"
  touch "$cCredentialsFile"
  chmod 600 "$cCredentialsFile"
  printf '%s\n' \
    "# ainonyproxy - credentials created by the installer" \
    "# Created: $(fNowStorage) (UTC)" \
    "" \
    "Dashboard:           https://<this-server>:$cHttpsPort/auth/login/" \
    "Dashboard user:      $cAdminUser" \
    "Dashboard password:  $pPassword" \
    "Dashboard role:      admin" \
    "" \
    "Linux user:          $cAppUser (system account: no password and no login shell)" \
    > "$cCredentialsFile"
  fLog "Credentials written to $cCredentialsFile"
}

fInitializeAdminUser() {
  local vPassword
  if fRunApp --user-exists "$cAdminUser"; then
    fLog "The dashboard administrator '$cAdminUser' already exists: its password is not changed"
    return 0
  fi
  fLog "Creating the dashboard administrator '$cAdminUser'"
  vPassword="$(fGeneratePassword)"
  printf '%s\n' "$vPassword" | fRunApp --set-user "$cAdminUser" --role admin --password-stdin
  fWriteCredentialsFile "$vPassword"
}

fInstallService() {
  fLog "Installing the OpenRC service $cServiceFile"
  printf '%s\n' \
    "#!/sbin/openrc-run" \
    "" \
    "name=\"$cAppName\"" \
    "description=\"ainonyproxy - Smart LLM proxy with privacy\"" \
    "command=\"$cVenvDir/bin/python3\"" \
    "command_args=\"$cWebAppDir/backend/ainonyproxy.py\"" \
    "command_user=\"$cAppUser:$cAppGroup\"" \
    "command_background=\"yes\"" \
    "directory=\"$cWebAppDir/backend\"" \
    'pidfile="/run/${RC_SVCNAME}.pid"' \
    "output_log=\"$cLogsDir/$cAppName.log\"" \
    "error_log=\"$cLogsDir/$cAppName.log\"" \
    "retry=\"TERM/30/KILL/5\"" \
    "" \
    "export AINONYPROXY_HOME=\"$cHomeDir\"" \
    "export PYTHONDONTWRITEBYTECODE=1" \
    "export PYTHONUNBUFFERED=1" \
    "" \
    "depend() {" \
    "  use net" \
    "  after firewall" \
    "}" \
    "" \
    "start_pre() {" \
    "  checkpath --file --owner $cAppUser:$cAppGroup --mode 0640 \"$cLogsDir/$cAppName.log\"" \
    "}" \
    > "$cServiceFile"
  chmod 755 "$cServiceFile"
  if fHasOpenRc && ! rc-update show default 2> /dev/null | grep -qw "$cAppName"; then
    rc-update add "$cAppName" default
  fi
}

fStartManualProcess() {
  local vCommand
  touch "$cLogsDir/$cAppName.log"
  chown "$cAppUser:$cAppGroup" "$cLogsDir/$cAppName.log"
  vCommand="cd '$cWebAppDir/backend' && exec env AINONYPROXY_HOME='$cHomeDir' PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 '$cVenvDir/bin/python3' '$cWebAppDir/backend/ainonyproxy.py'"
  setsid su -s /bin/sh -c "$vCommand" "$cAppUser" >> "$cLogsDir/$cAppName.log" 2>&1 < /dev/null &
  printf '%s\n' "$!" > "$cRunDir/$cAppName.pid"
  chown "$cAppUser:$cAppGroup" "$cRunDir/$cAppName.pid"
}

fStartService() {
  fPrepareOpenRc
  if fHasOpenRc && rc-service "$cAppName" restart; then
    fLog "The $cAppName service is started"
  else
    fLog "OpenRC could not start the service (a container?): starting ainonyproxy without a service manager."
    fLog "It will not start by itself after a reboot: run this installer again to start it."
    fStartManualProcess
  fi
}

fVerifyInstallation() {
  local vAttempt
  local vCode=""
  fLog "Waiting for https://127.0.0.1:$cHttpsPort/api/ai/status (loading the spaCy models takes a while)"
  for vAttempt in $(seq 1 "$cVerifyAttempts"); do
    vCode="$(curl -sk -o /dev/null -w '%{http_code}' "https://127.0.0.1:$cHttpsPort/api/ai/status" || true)"
    if [[ "$vCode" == "200" ]]; then
      fLog "ainonyproxy answers: online"
      return 0
    fi
    sleep "$cVerifySleepSeconds"
  done
  fLog "WARNING: ainonyproxy did not answer in time (last HTTP code: $vCode)."
  fLog "Look at what it says in: $cLogsDir/$cAppName.log"
}

fPrintSummary() {
  local vAddress
  vAddress="$(ip -4 route get 1.1.1.1 2> /dev/null | sed -n 's/.* src \([0-9.]*\).*/\1/p' || true)"
  if [[ -z "$vAddress" ]]; then
    vAddress="localhost"
  fi
  fLog "------------------------------------------------------------"
  fLog "ainonyproxy is installed ($vMode)."
  fLog "  Dashboard:    https://$vAddress:$cHttpsPort/auth/login/"
  fLog "  HTTP:         http://$vAddress:$cHttpPort (permanent redirect to HTTPS)"
  fLog "  AI API:       https://$vAddress:$cHttpsPort/api/ai/{provider}"
  fLog "  API docs:     https://$vAddress:$cHttpsPort/api/doc/"
  fLog "  Credentials:  $cCredentialsFile"
  fLog "  Install log:  $cInstallLogFile"
  fLog "  API keys:     $cConfigDir/api_keys.json (restart the service after editing it)"
  if fHasOpenRc; then
    fLog "  Service:      rc-service $cAppName status|restart|stop"
  fi
  fLog "------------------------------------------------------------"
}

fRunSteps() {
  umask 022
  fParseArguments "$@"
  fCheckRoot
  fCheckDistro
  fLog "ainonyproxy installer for Alpine Linux: $vMode"

  if [[ "$vMode" == "update" && ! -d "$cWebAppDir/backend" ]]; then
    fDie "ainonyproxy is not installed. Use --install."
  fi

  if [[ "$vMode" == "reinstall" ]]; then
    fConfirmReinstall
    fStopService
    fRemoveInstallation
  fi

  fInstallDependencies
  fCheckPythonVersion
  fCreateAppUser
  fCreateDirectories
  fObtainSourceCode
  fStopService
  fDeploySourceCode
  fInstallDefaultConfig
  fBuildVirtualEnv
  fInstallSpacyModels
  fGenerateCertificates
  fInitializeAdminUser
  fSetPermissions
  fInstallService
  fStartService
  fVerifyInstallation
  fPrintSummary
}

fMain() {
  local -a aFunctionNames
  local -a aVariableNames

  if [[ "$(id -u)" -eq 0 ]]; then
    fStartLogging
  fi
  vTempDir="$(mktemp -d)"

  # The steps run in a new bash, where `set -e` works (see the header)
  mapfile -t aFunctionNames < <(compgen -A function)
  export -f "${aFunctionNames[@]}"
  mapfile -t aVariableNames < <(compgen -v | grep -E '^[cv][A-Z]')
  export "${aVariableNames[@]}"
  "$BASH" -c 'set -euo pipefail; fRunSteps "$@"' "$0" "$@" < /dev/null
}

if ! fMain "$@"; then
  fLog "ERROR: the process did not finish. The cause is above, and in $cInstallLogFile"
  exit 1
fi
