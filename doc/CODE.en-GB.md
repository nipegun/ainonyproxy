# ainonyproxy - CODE

This CODE is also available in:\
en-GB, [en-US](CODE.md), [es-AR](CODE.es-AR.md), [es-ES](CODE.es-ES.md), [fr-FR](CODE.fr-FR.md)

Technical reference of ainonyproxy, for developers and for AI models. It is meant to be read surgically: jump to the section you need, do not read it end to end.

## Index

1. [Architecture and design decisions](#1-architecture-and-design-decisions)
2. [Module map](#2-module-map)
3. [Key symbol index](#3-key-symbol-index)
4. [Main flows](#4-main-flows)
5. [Entry point and route map](#5-entry-point-and-route-map)
6. [Impact analysis](#6-impact-analysis)
7. [Extension points](#7-extension-points)

---

## 1. Architecture and design decisions

### What it is

ainonyproxy is a FastAPI application that sits between a chat client and an LLM provider. For every request it detects personal data (PII) with an integrated Presidio, replaces it with markers such as `<PERSON_1>`, sends the masked conversation to the provider, and puts the real values back in the answer before returning it. Requests, statistics and dashboard users live in one SQLite database.

### One process, two listeners

The process always listens on two ports:

| Port | What answers | Why |
|---|---|---|
| `11080` (HTTP) | A tiny FastAPI app built by `fCreateRedirectApp` | Only answers `308 Permanent Redirect` to the same path on HTTPS. 308 (not 301) keeps the method and the body, so a client that POSTs to HTTP by mistake is not turned into a GET. |
| `11443` (HTTPS) | The real application, `vApp` | Everything: API, dashboards, docs. |

HTTPS is never optional. The certificate is chosen in this order: Let's Encrypt files in `/opt/ainonyproxy/certificates/` (`fullchain.pem` + `privkey.pem`), then the files named in `config.json` (`server.ssl`), then a self-signed certificate (`selfsigned-fullchain.pem` + `selfsigned-privkey.pem`) that the installer, or the application itself with `openssl`, creates when it is missing.

With `server.proxy_protocol: true` both listeners run under Hypercorn, which understands the PROXY protocol that HAProxy sends with `send-proxy`. Otherwise both run under Uvicorn in the same event loop.

The software is meant to be used from the same computer it runs on, so there is no proxy configuration to choose.

### Everything the application stores lives in `/opt/ainonyproxy/`

| Path | Content | Mode |
|---|---|---|
| `/opt/ainonyproxy/webapp/` | Code: `backend/` and `frontend/` copied from the repository | owner `ainonyproxy` |
| `/opt/ainonyproxy/venv/` | Python virtual environment | owner `ainonyproxy` |
| `/opt/ainonyproxy/config/` | `config.json`, `api_urls.json`, `api_keys.json`, `api_models.json`, `pii_detection.json` | `700`, files `600` |
| `/opt/ainonyproxy/db/ainonyproxy.db` | SQLite: `request_logs`, `users`, `user_sessions`, `app_settings` | `700`, file `600` |
| `/opt/ainonyproxy/certificates/` | Let's Encrypt or self-signed certificate | `700`, keys `600` |
| `/opt/ainonyproxy/logs/` | Output of the process when it does not run under systemd | `750` |
| `/opt/ainonyproxy/run/` | PID file when it runs without a service manager | `750` |

`config.py` builds every path from `cHomeDir`, which is `/opt/ainonyproxy` unless the environment variable `AINONYPROXY_HOME` says otherwise (only used to run the code from a checkout). The configuration in the repository (`backend/config-defaults/`) is only a template: the installer copies each file into `/opt/ainonyproxy/config/` when it does not exist yet, so an update never overwrites what the user changed.

The process runs as the system user `ainonyproxy` (no password, no login shell), the only one apart from root that can read the configuration, the database and the keys.

### Configuration split in several files

`fLoadConfig` reads `config.json` and then overwrites two sections with their own files: `providers` is built from `api_urls.json` (URL, format, default model) plus `api_keys.json` (keys), and `pii_detection` comes from `pii_detection.json`. Keys live apart so that the file with secrets can be `600` and is never shown or copied with the rest. Every string can use `${VAR}` or `${VAR:-default}`, replaced from the environment.

When keys are missing, `fEnsureApiKeys` asks for them only if there is a terminal. Under systemd or OpenRC there is none, so it writes empty entries and goes on: a service must never wait for input.

### PII detection: only the last user message decides

`PiiDetector.mAnalyzeMessages` scans only the last `user` message with content. If it has no PII, the conversation goes out as it is. If it has PII, `mAnalyzeAllMessages` scans every `user` and `assistant` message (with the language detected for the last one) and `fMaskMessages` masks all of them with one shared `MaskingContext`, so the same value gets the same marker everywhere in the conversation. This keeps the cost of the common case (no PII) at one scan.

Language detection (`langdetect`) only chooses which Presidio pipeline to use. If the detected language is not configured, the fallback language is used and the request is flagged (`X-Ainonyproxy-Language-Fallback`).

At startup the application refuses to run if a configured language has no spaCy model installed: detecting PII with the wrong model would silently let data through.

### Unmasking

`fUnmaskText` replaces markers from the longest to the shortest, so `<PERSON_10>` is never broken by `<PERSON_1>`. In streaming, `fUnmaskStreamFragment` keeps in a buffer everything after a `<` that has no `>` yet, because a marker can arrive split in two chunks; `fFlushStreamBuffer` empties it at the end.

### What is written to the database

`fCreateLogData` obeys two switches of `config.json` (`logging`):

| Switch | Columns it controls | Default |
|---|---|---|
| `log_content` | `original_content`, `client_response` (real, unmasked texts) | `false` |
| `log_masked_content` | `masked_content`, `provider_response` (masked texts) | `true` |

So by default the database never holds the personal data itself. `fPeriodicCleanupTask` deletes requests older than `retention_days` once at startup and then every 24 hours.

### Dates

The native format is the storage format of the rules: UTC, `2026-10-29@13-59-59.723`. It is what `services/dates.py` produces (`fNowStorage`) and what SQLite produces by itself as a column default (`cSqliteStorageNow`). The format sorts as text, so "the last hour" and "older than 30 days" are plain string comparisons. The interface shows `2026/10/29@13:59:59.723` (`fStorageToDisplay` in Python, `fStorageDateToDisplay` in JavaScript). Any other format must be derived from the native one with a function, never written by hand.

### Dashboard users and sessions

Two roles: `admin` and `user`. Passwords are stored as PBKDF2-SHA256 (600 000 iterations, random salt). A login creates a random token: the browser keeps it in the cookie `ainonyproxy_session` (`Secure`, `HttpOnly`, `SameSite=Strict`) and the database keeps only its SHA-256 (`user_sessions.token_hash`), so a copy of the database does not hand out valid sessions. Changing a password closes the other sessions of that account; an administrator setting a password for somebody closes all of theirs. The last administrator cannot be deleted.

`/api/auth/login` allows 5 failed attempts per client address every 15 minutes (in memory). A login for a user that does not exist does the same PBKDF2 work as a real one, so the answer time does not reveal which users exist.

Accounts can also be created at `/auth/register/` while the setting `registration_open` (table `app_settings`, `services/settings.py`) is true, which is its default; they always get the role `user`. `/api/auth/register` allows 5 accounts per client address every hour (in memory).

Every account can have one recovery code (`fGenerateRecoveryCode`: 20 characters of a 32-character alphabet, 100 random bits). Like the session tokens, only its SHA-256 is stored (`users.recovery_code_hash`); it is compared in constant time, and `UserStore.mRecoverPassword` spends it: new password, every session closed, new code returned. `/api/auth/recover` counts its failures in the same brake as the login. A code is shown only once: at the registration, to the administrator who creates a user, when the user generates a new one in Account (it asks for the current password) and after a recovery.

Settings changed from the dashboard live in `app_settings` and not in `config.json`, so saving them never rewrites the files that the user edits by hand (and their `${VAR}` references).

The very first start without any user (only possible when running without the installer) creates `admin` with a random password and prints it once.

### Security decisions

- CORS allows any origin but **without credentials**: a web page on another site can call the AI API, but can never ride on the dashboard session of whoever visits it. `SameSite=Strict` stops the cookie from travelling on cross-site requests anyway.
- Every value that comes from the server or from a user is escaped with `fEscapeHtml` before going into `innerHTML` (the model name of a request used to be an XSS).
- The `next` parameter of the login only accepts paths of this same site (`fIsSafeNextPath`), so the login cannot be used to redirect somewhere else.
- Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and `Referrer-Policy: same-origin`.
- `fFreePort` stops whatever still listens on 11080 or 11443 before listening (a previous instance left behind), as the rules ask.

### Why the installers run their steps in a new bash

The rules require `set -euo pipefail` and ending with `if ! fMain; then ... fi`. But a function called as the condition of an `if` runs with `set -e` suspended, and so does everything it calls, even a background child (measured with bash 5.2). `fMain` therefore exports every function and every `c*`/`v*` variable and runs `fRunSteps` in a new `bash -c 'set -euo pipefail; ...'`, which gets `set -e` back: the first command that fails stops the installation, and `if ! fMain` reports it. `deploy/run.sh` does the same.

### Why the installers can be piped from curl

The installers are meant to be run as `curl -fsSL <raw URL> | bash -s -- --install`, straight from the GitHub repository, and to be idempotent: running one twice with the same option leaves the system as running it once (every step checks before it acts: existing user, existing configuration files, existing certificate, existing administrator). What makes the pipe safe:

- Bash runs a piped script while it is still arriving. The top level only defines constants and functions, and the last line (`if ! fMain "$@"; then ... fi`) runs them, so a download cut halfway runs nothing.
- The standard input of the piped bash is the script itself. `fRunSteps` runs with its standard input on `/dev/null`, so no command (apt, pip, python) can swallow the rest of the script. The only question, `--reinstall` without `--yes`, reads `/dev/tty`, and without a terminal it stops and asks for `--yes`.
- `vScriptPath` (`BASH_SOURCE[0]`) is empty in a pipe, so `fObtainSourceCode` downloads `cSourceTarballUrl` (branch `main` of `github.com/nipegun/ainonyproxy`). Run from a copy of the repository, it uses that copy.
- Piped to `sh` instead of `bash`, a POSIX check right after `set -euo pipefail` stops it and shows the right command line.
- The apt of Debian never asks anything (`DEBIAN_FRONTEND=noninteractive`, `--force-confdef --force-confold`) and waits up to 10 minutes for the lock of another apt (`DPkg::Lock::Timeout=600`).
- `fCleanup` closes the pipe to `tee` and waits for it (5 s at most), so the last lines are not printed after the prompt.

### Interface languages

The texts live in `frontend/lang/<code>.json` (`en-GB`, `en-US`, `es-AR`, `es-ES`, `fr-FR`). `en-US.json` is the source and the markup carries the en-US text as fallback, so a missing key shows English instead of a key name. `/api/languages` lists them sorted by code (which is the alphabetical order the rules ask for), and the choice is remembered in `localStorage` (`ainonyproxy_lang`).

### Light and dark theme

Every page includes `partials/theme-head.html` in its `<head>`. It defines every colour as a CSS custom property three times: dark (`:root`, the default), light by system preference (`@media (prefers-color-scheme: light)` unless `data-theme="dark"`) and light chosen (`:root[data-theme="light"]`). No rule of the pages writes a colour directly, except the brand gradients and glows, which work on both themes. A tiny inline script sets `data-theme` on `<html>` from `localStorage` (`ainonyproxy_theme`) before the first paint, so the page never flashes the other theme. Without a saved choice there is no `data-theme` and the page follows the system theme, also when it changes while the page is open. `partials/theme-script.html` draws the switch (System / Light / Dark) with `fRenderThemeSwitch` and saves the choice with `fSetTheme`; the `storage` event carries it to the other open tabs.

### Pages without a session

`login.html`, `register.html` and `recover.html` extend `auth-base.html`, which holds their styles, the language row, the theme switch and the shared script (`fTranslateOr`, `fErrorTextFromData`, `fIsSafeRedirect`, `fCopyCode`). Each page sets `vPageTitleKey` and `vPageTitleFallback` and fills the blocks `content` and `scripts`.

---

## 2. Module map

| Module | Path | Responsibility | Depends on | Used by |
|---|---|---|---|---|
| Entry point | `backend/ainonyproxy.py` | Builds `vApp`, middleware, routers, certificates, ports, startup checks, CLI for users | `config`, every `routes/*`, `services.logger`, `services.users`, `services.port_guard` | systemd/OpenRC, `deploy/run.sh`, installers |
| Configuration | `backend/config.py` | Paths under `/opt/ainonyproxy/`, Pydantic models, loading and saving the JSON files | `pydantic` | everything |
| AI routes | `backend/routes/chat.py` | `/api/ai/` (list) and `/api/ai/{provider}` (chat), SSE unmasking | `services.decision`, `services.masking`, `services.logger`, `services.dates` | `ainonyproxy.py` |
| Status | `backend/routes/health.py` | `/api/ai/status` | `services.decision` | `ainonyproxy.py`, installers (verification) |
| Info | `backend/routes/info.py` | `/api/ai/info` | `config`, `services.decision`, `services.pii_detector` | `ainonyproxy.py` |
| Auth routes | `backend/routes/auth.py` | `/auth/login/`, `/auth/register/` and `/auth/recover/` pages, `/api/auth/*`, brute force and registration brakes | `services.auth`, `services.users`, `services.settings`, `routes.users` (`fUserErrorToHttp`) | `ainonyproxy.py` |
| Dashboard routes | `backend/routes/dashboard.py` | `/`, `/admin/dashboard/*`, `/user/dashboard/*`, `/api/admin/logs`, `/api/admin/stats`, `/api/languages*` | `services.auth`, `services.logger`, `config` | `ainonyproxy.py` |
| User routes | `backend/routes/users.py` | `/api/admin/users*`, `/api/admin/registration`, `/api/user/account*` | `services.auth`, `services.users`, `services.settings` | `ainonyproxy.py`, `routes/auth.py` |
| Decision | `backend/services/decision.py` | `Router`: one `LlmClient` per provider, decides whether to mask | `services.pii_detector`, `services.masking`, `services.llm_client` | `routes/chat.py`, `routes/health.py`, `routes/info.py` |
| PII detector | `backend/services/pii_detector.py` | Scans messages, validates spaCy models | `presidio.analyzer`, `services.language_detector` | `services.decision`, `ainonyproxy.py`, `routes/info.py` |
| Language detector | `backend/services/language_detector.py` | `langdetect` + fallback | `config` | `services.pii_detector` |
| Masking | `backend/services/masking.py` | Masking, unmasking, streaming buffer | `services.pii_detector` (types) | `services.decision`, `routes/chat.py` |
| LLM client | `backend/services/llm_client.py` | HTTP to OpenAI-compatible and Anthropic APIs, streaming | `httpx` | `services.decision` |
| Request logger | `backend/services/logger.py` | `request_logs`, statistics, cleanup; `fOpenDatabase` | `config`, `services.dates` | `routes/chat.py`, `routes/dashboard.py`, `services.users`, `ainonyproxy.py` |
| Users | `backend/services/users.py` | `users`, `user_sessions`, password hashing, recovery codes | `services.logger` (`fOpenDatabase`), `services.dates` | `services.auth`, `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Settings | `backend/services/settings.py` | `app_settings`: settings changed from the dashboard (`registration_open`) | `services.logger` (`fOpenDatabase`), `services.dates` | `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Auth helpers | `backend/services/auth.py` | Session cookie, current user, guards, login redirect | `services.users`, `config` | `routes/auth.py`, `routes/dashboard.py`, `routes/users.py` |
| Dates | `backend/services/dates.py` | Storage/display date formats | - | `logger`, `users`, `chat`, `view_database.py` |
| Port guard | `backend/services/port_guard.py` | Frees a TCP port through `/proc` | - | `ainonyproxy.py` |
| Presidio wrapper | `backend/presidio/analyzer.py` | `AnalyzerEngine` with one spaCy model per language | `presidio_analyzer`, `config` | `services.pii_detector` |
| spaCy models | `backend/presidio/setup.py` | Installs the spaCy models | `pip` | installers, `deploy/run.sh` |
| DB viewer | `backend/view_database.py` | Interactive terminal viewer of the database | `config`, `services.dates` | humans |
| Dashboard page | `frontend/templates/dashboard.html` | Both dashboards (Jinja2 + vanilla JS) | `/api/*` | `routes/dashboard.py` |
| Pages without a session | `frontend/templates/auth-base.html` + `login.html`, `register.html`, `recover.html` | Login, registration and password recovery forms | `/api/auth/*`, `/api/languages*` | `routes/auth.py` |
| Theme | `frontend/templates/partials/theme-head.html`, `partials/theme-script.html` | Colours of both themes and the theme switch | - | every page |
| Texts | `frontend/lang/*.json` | Interface translations | - | every page |
| Installers | `deploy/install-update-reinstall-{debian,alpine}.sh` | Install, update, reinstall | repository or GitHub tarball | root |
| Manual launcher | `deploy/run.sh` | venv, dependencies, defaults, models, start in the foreground | `backend/` | humans |

---

## 3. Key symbol index

| Symbol | File:line | What it does |
|---|---|---|
| `vApp` | `backend/ainonyproxy.py:288` | The FastAPI application (docs in `/api/doc/`) |
| `fMain` | `backend/ainonyproxy.py:404` | Entry point: CLI or certificates + ports + servers |
| `fRunCommandLine` | `backend/ainonyproxy.py:366` | `--user-exists`, `--list-users`, `--set-user` |
| `fLifespan` | `backend/ainonyproxy.py:242` | Startup checks, first admin, banner, cleanup task |
| `fValidateStartup` | `backend/ainonyproxy.py:120` | Initialises Presidio and stops when models are missing |
| `fEnsureSelfSignedCertificate` | `backend/ainonyproxy.py:54` | Creates the self-signed certificate with `openssl` |
| `fCreateRedirectApp` | `backend/ainonyproxy.py:87` | HTTP app that answers 308 to HTTPS |
| `fRequestIdMiddleware` | `backend/ainonyproxy.py:312` | `X-Request-ID` and security headers |
| `cHomeDir` | `backend/config.py:20` | `/opt/ainonyproxy` (or `AINONYPROXY_HOME`) |
| `AppConfig` | `backend/config.py:111` | Root Pydantic model of the configuration |
| `fLoadConfig` | `backend/config.py:341` | Reads `config.json` + `api_urls.json` + `api_keys.json` + `pii_detection.json` |
| `fGetConfig` | `backend/config.py:407` | Configuration singleton |
| `fEnsureApiKeys` | `backend/config.py:263` | Asks for missing keys only with a terminal |
| `fChatCompletions` | `backend/routes/chat.py:127` | `POST /api/ai/{provider}`: detect, mask, call, unmask, log |
| `fCreateLogData` | `backend/routes/chat.py:56` | Builds the log row, obeying `log_content` / `log_masked_content` |
| `fCreateUnmaskedStream` | `backend/routes/chat.py:261` | Unmasks an SSE stream |
| `fListProviders` | `backend/routes/chat.py:100` | `GET /api/ai/` |
| `Router.mDecide` | `backend/services/decision.py:55` | Scan + mask decision for a conversation |
| `PiiDetector.mAnalyzeMessages` | `backend/services/pii_detector.py:78` | Scans the last user message |
| `PiiDetector.mAnalyzeAllMessages` | `backend/services/pii_detector.py:123` | Scans every user/assistant message |
| `PiiDetector.mValidateLanguages` | `backend/services/pii_detector.py:222` | Which configured languages have their model |
| `fMask` | `backend/services/masking.py:38` | Replaces entities with markers |
| `fUnmaskText` | `backend/services/masking.py:87` | Puts the original values back |
| `fUnmaskStreamFragment` | `backend/services/masking.py:126` | Streaming unmasking with a buffer |
| `LlmClient.mCompleteChat` | `backend/services/llm_client.py:198` | Sends the request (OpenAI-compatible or Anthropic) |
| `RequestLogger` | `backend/services/logger.py:75` | `request_logs` table, statistics, cleanup |
| `fOpenDatabase` | `backend/services/logger.py:49` | Opens SQLite creating its folder with mode 700 |
| `UserStore` | `backend/services/users.py:106` | Users and sessions |
| `UserStore.mAuthenticate` | `backend/services/users.py:252` | Checks credentials in constant time |
| `UserStore.mCreateSession` | `backend/services/users.py:331` | New session token (only its hash is stored) |
| `fHashPassword` | `backend/services/users.py:50` | PBKDF2-SHA256 |
| `UserStore.mNewRecoveryCode` | `backend/services/users.py:273` | New recovery code for a user (only its SHA-256 is stored) |
| `UserStore.mRecoverPassword` | `backend/services/users.py:288` | Spends a recovery code: new password, sessions closed, new code |
| `fGenerateRecoveryCode` | `backend/services/users.py:73` | `XXXXX-XXXXX-XXXXX-XXXXX`, 100 random bits |
| `SettingsStore` | `backend/services/settings.py:29` | `app_settings` table (settings changed from the dashboard) |
| `dSettingDefaults` | `backend/services/settings.py:24` | Value of each setting while nobody has changed it |
| `fGetCurrentUser` | `backend/services/auth.py:27` | User of the session cookie |
| `fRequireApiAdmin` | `backend/services/auth.py:70` | 401/403 guard for `/api/admin/*` |
| `fLoginRedirect` | `backend/services/auth.py:54` | 303 to `/auth/login/?next=...` |
| `fIsSafeNextPath` | `backend/services/auth.py:40` | Only same-site destinations after the login |
| `fApiLogin` | `backend/routes/auth.py:137` | `POST /api/auth/login` (brute force brake) |
| `fApiRegister` | `backend/routes/auth.py:157` | `POST /api/auth/register` (open?, brake, user, recovery code, session) |
| `fApiRecover` | `backend/routes/auth.py:188` | `POST /api/auth/recover` (same brute force brake as the login) |
| `fApiNewRecoveryCode` | `backend/routes/users.py:115` | `POST /api/user/account/recovery-code` |
| `fApiSetRegistration` | `backend/routes/users.py:95` | `PUT /api/admin/registration` |
| `fAdminDashboardTab` | `backend/routes/dashboard.py:75` | Renders `/admin/dashboard/<tab>/` |
| `fUserDashboardTab` | `backend/routes/dashboard.py:95` | Renders `/user/dashboard/<tab>/` |
| `aAdminTabs` / `aUserTabs` | `backend/routes/dashboard.py:35` | Tabs of each dashboard (the first one is the default) |
| `fNowStorage` | `backend/services/dates.py:31` | Now, in the storage format |
| `fStorageToDisplay` | `backend/services/dates.py:56` | Storage format to display format |
| `fFreePort` | `backend/services/port_guard.py:63` | Stops whatever listens on a port |
| `PiiAnalyzer.mInitialize` | `backend/presidio/analyzer.py:63` | Builds the Presidio engine with the spaCy models |
| `fEscapeHtml` (JS) | `frontend/templates/dashboard.html`, `auth-base.html` | Escapes every dynamic value before `innerHTML` |
| `fStorageDateToDisplay` (JS) | `frontend/templates/dashboard.html` | Date display format in the browser |
| `fSetTheme` / `fRenderThemeSwitch` (JS) | `frontend/templates/partials/theme-script.html` | Saves the theme choice and draws the switch |
| Theme tokens (CSS) | `frontend/templates/partials/theme-head.html` | Colours of the dark and light themes |
| `fCopyCode` (JS) | `frontend/templates/auth-base.html`, `dashboard.html` | Copies a recovery code, or selects it when there is no clipboard access |
| `fRunSteps` (bash) | `deploy/install-update-reinstall-*.sh` | Ordered list of installation steps |
| `fMain` (bash) | `deploy/install-update-reinstall-*.sh` | Logging + runs `fRunSteps` in a new bash |
| `fObtainSourceCode` (bash) | `deploy/install-update-reinstall-*.sh` | Code of the local copy of the repository, or the GitHub tarball when the script arrives through a pipe |
| `fCleanup` (bash) | `deploy/install-update-reinstall-*.sh` | `EXIT` trap: deletes the downloaded code and waits for `tee` |

---

## 4. Main flows

### Chat request (`POST /api/ai/{provider}`)

1. `fChatCompletions` (`routes/chat.py`) checks the provider with `Router.mProviderExists` and validates the body with `ChatRequestSchema`.
2. `Router.mDecide` → `PiiDetector.mAnalyzeMessages` → `LanguageDetector.mDetect` → `PiiDetector.mDetectPii` → `PiiAnalyzer.mAnalyze` (Presidio).
3. With PII: `Router._mDecideMask` → `PiiDetector.mAnalyzeAllMessages` → `fMaskMessages` → `fMask` for each message.
4. `Router.mGetClient(provider).mCompleteChat(masked request)` → `_mCompleteChatJson` / `_mCompleteChatJsonAnthropic` / `_mCompleteChatStreaming` / `_mCompleteChatStreamingAnthropic`.
5. JSON answer: `fUnmaskResponse` → `fLogRequest(fCreateLogData(...))` → `JSONResponse` with the `X-Ainonyproxy-*` headers.
6. Streaming answer: `fLogRequest` first (no answer text), then `StreamingResponse(fCreateUnmaskedStream(...))` → `fUnmaskStreamFragment` per chunk → `fFlushStreamBuffer` at the end.
7. Errors: unknown provider 404, invalid body 400, Presidio failure 503, provider failure 502.

### Startup (`python3 ainonyproxy.py`)

1. `fMain` → `fParseArguments` (CLI options exit here) → `fEnsureApiKeys` → `fGetConfig`.
2. Certificate: `fDetectCertificates` → `server.ssl` → `fEnsureSelfSignedCertificate`.
3. `fFreePort(11080)`, `fFreePort(11443)`.
4. Uvicorn (or Hypercorn with `proxy_protocol`) starts `fCreateRedirectApp(11443)` on 11080 and `vApp` on 11443.
5. `fLifespan` → `fValidateStartup` (Presidio + models, exits when a model is missing) → `fEnsureAdminUser` → `fPrintStartupBanner` → `fPeriodicCleanupTask`.

### Login

1. `GET /admin/dashboard/overview/` without a session → `fAdminDashboardTab` → `fLoginRedirect` → `303 /auth/login/?next=%2Fadmin%2Fdashboard%2Foverview%2F`.
2. `fLoginPage` renders `login.html` with `vNext` (only if `fIsSafeNextPath`).
3. The form calls `POST /api/auth/login` → `fApiLogin` → `UserStore.mAuthenticate` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON with `redirect` (the `next` path, or the dashboard of the role).
4. Every later page or API call → `fGetCurrentUser` → `UserStore.mGetSessionUser`.

### Registration

1. `GET /auth/register/` → `fRegisterPage` → `register.html` with `vRegistrationOpen` (`SettingsStore.mIsRegistrationOpen`). A logged in user is sent to their dashboard.
2. The form calls `POST /api/auth/register` → `fApiRegister`: 403 `registration_closed`, or 429 after 5 accounts per address and hour → `UserStore.mCreateUser` (role `user`) → `UserStore.mNewRecoveryCode` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON with `recovery_code` and `redirect`.
3. The page shows the code once; "Go to my dashboard" follows `redirect`.

### Password recovery

1. `GET /auth/recover/` → `fRecoverPage` → `recover.html`.
2. `POST /api/auth/recover` → `fApiRecover` → brute force brake (`fRecentFailures`) → `UserStore.mRecoverPassword`: validates the new password, compares the SHA-256 of the code in constant time and, in one `UPDATE ... WHERE recovery_code_hash = <old hash>`, sets the new password and a new code; then deletes every session of the user.
3. Wrong user or code → 400 `invalid_recovery_code` and one failure more. Right → JSON with the new `recovery_code`, shown once.

### Dashboard tab

`/admin/dashboard/` → 307 to `/admin/dashboard/overview/` (first of `aAdminTabs`). `fAdminDashboardTab` checks session and role and renders `dashboard.html` with `vRole`, `vTab`, `aTabs`. The page script reads `data-tab` and loads only what that tab needs: `overview` → `/api/admin/stats` + `/api/admin/logs` every 5 s; `users` → `/api/admin/registration` + `/api/admin/users`; `account` → `/api/user/account`; `api` → `/api/ai/`; `help` → rendered locally.

### Installation (`install-update-reinstall-debian.sh --install`)

`fMain` → `fStartLogging` (tee to `/root/webapp-install.log`) → new bash → `fRunSteps`: `fParseArguments` → `fCheckRoot` → `fCheckDistro` → (`--reinstall`: `fConfirmReinstall` → `fStopService` → `fRemoveInstallation`) → `fInstallDependencies` → `fCheckPythonVersion` → `fCreateAppUser` → `fCreateDirectories` → `fObtainSourceCode` (local copy or GitHub tarball) → `fStopService` → `fDeploySourceCode` → `fInstallDefaultConfig` → `fBuildVirtualEnv` → `fInstallSpacyModels` → `fGenerateCertificates` → `fInitializeAdminUser` (`ainonyproxy.py --user-exists` / `--set-user --password-stdin`, then `fWriteCredentialsFile`) → `fSetPermissions` → `fInstallService` → `fStartService` (systemd/OpenRC, or a plain process in containers without them) → `fVerifyInstallation` (polls `/api/ai/status`) → `fPrintSummary`.

On exit, `fCleanup` deletes the downloaded code and waits for `tee` to write the last lines.

---

## 5. Entry point and route map

### Web

| Route | Handler | File | Access |
|---|---|---|---|
| `GET /` | `fRoot` | `backend/routes/dashboard.py` | Redirects to login or to the dashboard of the role |
| `GET /auth/login/` | `fLoginPage` | `backend/routes/auth.py` | Public |
| `GET /auth/register/` | `fRegisterPage` | `backend/routes/auth.py` | Public (with the registration closed it shows a notice) |
| `GET /auth/recover/` | `fRecoverPage` | `backend/routes/auth.py` | Public |
| `GET /admin/dashboard/` | `fAdminDashboardRoot` | `backend/routes/dashboard.py` | admin → 307 to `overview/` |
| `GET /admin/dashboard/{overview,users,account,help}/` | `fAdminDashboardTab` | `backend/routes/dashboard.py` | admin |
| `GET /user/dashboard/` | `fUserDashboardRoot` | `backend/routes/dashboard.py` | any user → 307 to `api/` |
| `GET /user/dashboard/{api,account,help}/` | `fUserDashboardTab` | `backend/routes/dashboard.py` | any user |
| `GET /api/doc/` | FastAPI Swagger UI | `backend/ainonyproxy.py` | Public |
| `GET /api/doc/redoc/` | FastAPI ReDoc | `backend/ainonyproxy.py` | Public |
| `GET /api/doc/openapi.json` | FastAPI | `backend/ainonyproxy.py` | Public |
| `GET /api/ai/` | `fListProviders` | `backend/routes/chat.py` | Public |
| `POST /api/ai/{provider}` | `fChatCompletions` | `backend/routes/chat.py` | Public |
| `GET /api/ai/status` | `fStatus` | `backend/routes/health.py` | Public |
| `GET /api/ai/info` | `fInfo` | `backend/routes/info.py` | Public |
| `POST /api/auth/login` | `fApiLogin` | `backend/routes/auth.py` | Public |
| `POST /api/auth/register` | `fApiRegister` | `backend/routes/auth.py` | Public, while the registration is open |
| `POST /api/auth/recover` | `fApiRecover` | `backend/routes/auth.py` | Public |
| `POST /api/auth/logout` | `fApiLogout` | `backend/routes/auth.py` | Public |
| `GET /api/auth/session` | `fApiSession` | `backend/routes/auth.py` | any user |
| `GET /api/admin/logs?limit=&offset=` | `fApiLogs` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/stats` | `fApiStats` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/users` | `fApiListUsers` | `backend/routes/users.py` | admin |
| `POST /api/admin/users` | `fApiCreateUser` | `backend/routes/users.py` | admin |
| `GET /api/admin/registration` | `fApiGetRegistration` | `backend/routes/users.py` | admin |
| `PUT /api/admin/registration` | `fApiSetRegistration` | `backend/routes/users.py` | admin |
| `DELETE /api/admin/users/{username}` | `fApiDeleteUser` | `backend/routes/users.py` | admin |
| `PUT /api/admin/users/{username}/password` | `fApiResetPassword` | `backend/routes/users.py` | admin |
| `GET /api/user/account` | `fApiAccount` | `backend/routes/users.py` | any user |
| `PUT /api/user/account/password` | `fApiChangePassword` | `backend/routes/users.py` | any user |
| `POST /api/user/account/recovery-code` | `fApiNewRecoveryCode` | `backend/routes/users.py` | any user |
| `GET /api/languages` | `fApiLanguages` | `backend/routes/dashboard.py` | Public |
| `GET /api/languages/{code}` | `fApiLanguageFile` | `backend/routes/dashboard.py` | Public |
| `http://*:11080/*` | `fRedirectToHttps` | `backend/ainonyproxy.py` | 308 to HTTPS |

### Command line

| Command | Handler | File |
|---|---|---|
| `ainonyproxy.py` | `fMain` | `backend/ainonyproxy.py` |
| `ainonyproxy.py --user-exists NAME` | `fRunCommandLine` | `backend/ainonyproxy.py` |
| `ainonyproxy.py --list-users` | `fRunCommandLine` | `backend/ainonyproxy.py` |
| `printf 'PASS\n' \| ainonyproxy.py --set-user NAME --role admin --password-stdin` | `fRunCommandLine` | `backend/ainonyproxy.py` |
| `presidio/setup.py --languages en,es` | `fMain` | `backend/presidio/setup.py` |
| `view_database.py` | `fMain` | `backend/view_database.py` |
| `install-update-reinstall-debian.sh [--install\|--update\|--reinstall] [--yes]` | `fMain` | `deploy/` |
| `install-update-reinstall-alpine.sh [--install\|--update\|--reinstall] [--yes]` | `fMain` | `deploy/` |
| `run.sh` | `fMain` | `deploy/` |

---

## 6. Impact analysis

| If you change... | It affects... |
|---|---|
| `config.py` paths (`cHomeDir` and friends) | Installers (same paths hard-coded in their constants), `deploy/run.sh`, systemd/OpenRC units, every document that names `/opt/ainonyproxy/` |
| `AppConfig` and its sub-models | `backend/config-defaults/config.json`, `fSaveConfig`, MANUAL (configuration reference) |
| `api_urls.json` / `api_keys.json` format | `fLoadConfig`, `fEnsureApiKeys`, `fValidateApiKeys`, installers (`fInstallDefaultConfig`) |
| `services/dates.py` formats | Every stored date (`request_logs`, `users`, `user_sessions`), the string comparisons of statistics, cleanup and session expiry, `fStorageDateToDisplay` in the dashboard, `view_database.py` |
| `request_logs` columns | `RequestRecord`, `RequestLogData`, `mRecord`, `fCreateLogData`, `fApiLogs` consumers in `dashboard.html`, `view_database.py` |
| `users` / `user_sessions` tables | `UserStore` (its `_mInitializeDatabase` adds the missing columns to old databases), `view_database.py` (options 1 and 3), installers (`--user-exists`, `--set-user`) |
| `MaskingContext` or the marker format `<TYPE_N>` | `fMask`, `fUnmaskText`, `fUnmaskStreamFragment` (it looks for `<` and `>`), the marker highlighting regex in `dashboard.html` |
| `PiiDetectionResult` fields | `Router`, `fCreateLogData`, response headers in `fChatCompletions` |
| `LlmClient` return types | `fChatCompletions` (`is_streaming`, `response`, `model`) |
| Session cookie (`services/auth.py`) | Every guarded page and API, `login.html` and `register.html` (it logs the new user in), `fApi` in `dashboard.html` (redirect on 401) |
| `aAdminTabs` / `aUserTabs` | Sidebar of `dashboard.html`, `tabs.*` keys of every `frontend/lang/*.json`, MANUAL |
| Recovery code format (`cRecoveryCode*`, `fNormalizeRecoveryCode`) | Every stored code (a new format must keep accepting the old codes, or users must generate new ones), the placeholder of `recover.html`, MANUAL |
| `app_settings` / `dSettingDefaults` | `SettingsStore`, `/api/admin/registration`, the Users tab, `register.html` and `login.html` (link to the registration) |
| Theme tokens (`partials/theme-head.html`) | Every page. Each token is defined three times (dark, light by system preference, light chosen) and the three blocks must have the same names |
| A key of `en-US.json` | The same key in `en-GB`, `es-AR`, `es-ES`, `fr-FR` |
| Ports 11080 / 11443 | `config-defaults/config.json`, `fVerifyInstallation` and `fPrintSummary` in the installers, help texts (`help.endpointCode`), README, MANUAL |
| `ainonyproxy.py` CLI options | `fInitializeAdminUser` in both installers, MANUAL (password reset) |
| `cSourceTarballUrl`, the repository or its `main` branch | Both installers (header, `fObtainSourceCode`, the `sh` check), the install lines of every README and MANUAL |

---

## 7. Extension points

### A new LLM provider

- OpenAI-compatible: add `"name": {"url": "https://.../v1/chat/completions"}` to `/opt/ainonyproxy/config/api_urls.json` (and to `backend/config-defaults/api_urls.json` for new installations), add its key to `api_keys.json`, restart. It is served at `/api/ai/name`.
- Another wire format: add the value to `cApiFormat` (`config.py`), detect it in `fDetectFormat`, and add a branch in `LlmClient.mCompleteChat` that converts the request and the answer to the OpenAI shape (see the Anthropic branch: `_mBuildAnthropicBody`, `_mFormatAnthropicResponse`, `_mCompleteChatStreamingAnthropic`). `gemini` is declared but has no branch yet: it is sent as OpenAI-compatible.

### A new API endpoint

1. Add the function to the router of its audience: `vAdminApiRouter` / `vAdminUsersRouter` (`/api/admin`), `vUserAccountRouter` (`/api/user`), `vChatRouter` (`/api/ai`), or a new `APIRouter(tags=[...])` included in `ainonyproxy.py` with a prefix under `/api/`.
2. Guard it with `fRequireApiAdmin(pRequest)` or `fRequireApiUser(pRequest)`.
3. Give it a `summary`: it appears in `/api/doc/` by itself.
4. Add its row to section 5 of every CODE file.

### A new dashboard tab

1. Add its name to `aAdminTabs` or `aUserTabs` (`routes/dashboard.py`).
2. Add its icon to `dTabIcons` and its `{% if vTab == "name" %}` block to `dashboard.html`, and its loader to the start block of the script.
3. Add `tabs.name` (and its texts) to every `frontend/lang/*.json`.
4. It is reachable at once at `/admin/dashboard/name/` or `/user/dashboard/name/`.

### A new interface language

Copy `frontend/lang/en-US.json` to `frontend/lang/xx-YY.json`, change `meta` and translate the values. It appears in the selector by itself.

### A new dashboard setting

Add its key and default to `dSettingDefaults` (`services/settings.py`) with a pair of methods like `mIsRegistrationOpen` / `mSetRegistrationOpen`, an admin endpoint like `fApiSetRegistration` under `/api/admin/`, and its control in the tab it belongs to (with its texts in every `frontend/lang/*.json`).

### A new colour

Add the custom property to the three blocks of `partials/theme-head.html` (dark, light by system preference, light chosen) and use it with `var(--name)`. Never write a colour directly in a page.

### A new PII language

Add its code to `languages` in `/opt/ainonyproxy/config/pii_detection.json` (it must be in `cSupportedLanguages`), then run `presidio/setup.py --languages xx` with the venv Python (or run the installer with `--update`) and restart.
