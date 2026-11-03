# ainonyproxy - MANUAL

This MANUAL is also available in:\
en-GB, [en-US](MANUAL.md), [es-AR](MANUAL.es-AR.md), [es-ES](MANUAL.es-ES.md), [fr-FR](MANUAL.fr-FR.md)

How to install ainonyproxy, set it up and use it day to day.

## Contents

1. [What it does](#what-it-does)
2. [What it runs on](#what-it-runs-on)
3. [Installing](#installing)
4. [Updating and reinstalling](#updating-and-reinstalling)
5. [Opening it](#opening-it)
6. [Logging in](#logging-in)
7. [The admin dashboard](#the-admin-dashboard)
8. [The user dashboard](#the-user-dashboard)
9. [Light and dark theme](#light-and-dark-theme)
10. [Sending requests through ainonyproxy](#sending-requests-through-ainonyproxy)
11. [Providers and API keys](#providers-and-api-keys)
12. [PII detection](#pii-detection)
13. [What is written to the database](#what-is-written-to-the-database)
14. [Configuration reference](#configuration-reference)
15. [Files and folders](#files-and-folders)
16. [Certificates](#certificates)
17. [Running it without the service](#running-it-without-the-service)
18. [Looking inside the database](#looking-inside-the-database)
19. [Troubleshooting](#troubleshooting)
20. [Uninstalling](#uninstalling)

---

## What it does

ainonyproxy is a privacy proxy for language models (LLMs). Your applications send their chat requests to ainonyproxy instead of sending them to OpenAI, Anthropic, DeepSeek, a local Ollama, etc. For each request ainonyproxy:

1. Detects personal information (names, e-mail addresses, phone numbers, IBANs, IP addresses, places, ID numbers...) with [Presidio](https://microsoft.github.io/presidio/) and spaCy, running on your own computer.
2. Replaces each piece of personal information with a marker such as `<PERSON_1>` or `<EMAIL_ADDRESS_1>`.
3. Sends the masked conversation to the provider you chose.
4. Puts the real values back into the answer before returning it to your application.

The provider never sees the personal data, and your application does not notice anything: it speaks the OpenAI chat API, with or without streaming.

It also has a web dashboard, with a light and a dark theme, that shows statistics and the latest requests and manages users (who can create their own account and recover their password by themselves).

## What it runs on

| | |
|---|---|
| Operating system | Debian 13 (trixie) or later, or Alpine Linux with a `python3` package of version 3.13 or later |
| Python | 3.13 or later (the installer checks it) |
| Disk | About 3 GB (Python packages and the spaCy language models) |
| Memory | 2 GB or more (each spaCy language model is loaded in memory) |
| Network | Access to the LLM providers you use, and to PyPI and GitHub during the installation |
| Ports | `11080` (HTTP, it only redirects) and `11443` (HTTPS) |

It is meant to be used from the same computer it runs on: your applications talk to `https://localhost:11443`.

## Installing

Run the installer as `root`. It does everything by itself and asks nothing.

**Debian** (a minimal Debian, such as the Docker image, has no curl, so the line installs it first):

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --install
```

**Alpine Linux** (it has no bash by default, so the line installs it first):

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install
```

You can also run it from a copy of the repository: `bash deploy/install-update-reinstall-debian.sh --install`. In that case it uses the code of that copy instead of downloading it.

Running it again is safe: the installers are idempotent, so running one twice with the same option leaves the system as running it once. They are made to be downloaded with `curl` and piped straight into `bash`: nothing runs until the whole script has arrived, so a download cut halfway does nothing. Pipe them to `bash`, not to `sh`: with `sh` they stop and tell you so.

### What the installer does

1. Installs the system packages it needs (Python, compiler, OpenSSL, curl...).
2. Checks that Python is 3.13 or later.
3. Creates the system user `ainonyproxy` (no password, no login shell), whose home is `/opt/ainonyproxy/`.
4. Copies the code to `/opt/ainonyproxy/webapp/` and creates the Python virtual environment in `/opt/ainonyproxy/venv/`.
5. Copies the default configuration to `/opt/ainonyproxy/config/` (only the files that do not exist yet: it never overwrites yours).
6. Installs the spaCy models of the languages configured in `pii_detection.json`.
7. Creates a self-signed certificate when there is no Let's Encrypt certificate.
8. Creates the dashboard administrator `admin` with a random password (only the first time).
9. Installs and starts the service (`systemd` on Debian, `OpenRC` on Alpine) and waits until it answers.

The first installation takes several minutes: the Python packages and the spaCy models are big. On Alpine some packages may have to be compiled, which takes longer.

### Where the password is

| File | Content |
|---|---|
| `/root/webapp-credentials.txt` | The user and password of the dashboard administrator |
| `/root/webapp-install.log` | Everything the installer did, with every command output |

Both can only be read by root (mode `600`).

### In containers

In a container without systemd (Docker), the installer starts ainonyproxy as a plain background process and warns you that it will not start by itself after a restart of the container: run the installer again to start it. On Alpine it prepares OpenRC so the service can run inside the container.

## Updating and reinstalling

| Command | What it does |
|---|---|
| `--install` | Installs. On an existing installation it behaves like `--update`. |
| `--update` | Replaces the code and updates the dependencies and models. Keeps configuration, database, users, certificates and passwords. |
| `--reinstall` | Deletes the code, the virtual environment, the configuration, the database and the logs (**not** the certificates) and installs again from zero, with a new administrator password. It asks for confirmation; add `--yes` to skip the question. |

```bash
curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --update
```

## Opening it

| What | Address |
|---|---|
| Dashboard | `https://localhost:11443/` (it takes you to the login) |
| Login | `https://localhost:11443/auth/login/` |
| Create an account | `https://localhost:11443/auth/register/` (when the registration is open) |
| Recover the password | `https://localhost:11443/auth/recover/` |
| AI API | `https://localhost:11443/api/ai/{provider}` |
| API documentation (Swagger) | `https://localhost:11443/api/doc/` |
| Status | `https://localhost:11443/api/ai/status` |

Anything that arrives at `http://...:11080` is redirected permanently to the same address on `https://...:11443`.

With the self-signed certificate the browser shows a warning the first time: it is expected, the connection is encrypted anyway. See [Certificates](#certificates) to use a real one.

## Logging in

Open the dashboard and log in with the user and password of `/root/webapp-credentials.txt`. If you open a dashboard address without being logged in, you are sent to the login and, after it, back to the page you asked for.

There are two roles:

| Role | What it can do |
|---|---|
| `admin` | Everything: both dashboards, statistics, request logs, user management |
| `user` | The user dashboard: connection data of the API, own password |

A session lasts 12 hours (`dashboard.session_hours`). After 5 failed attempts from the same address, the login waits 15 minutes.

### Creating an account

When the registration is open, anybody who reaches the login can create an account at `/auth/register/` (link "Create an account" of the login). These accounts always have the role `user`: only an administrator can make somebody `admin`. The registration is open by default, and an administrator opens or closes it in **Users → Registration**. One address can create up to 5 accounts per hour.

Right after creating the account, the page shows its recovery code once. When you confirm that you have saved it, "Go to my dashboard" opens the user dashboard, already logged in.

### Recovery codes

Every account can have one recovery code, such as `ABCDE-FGHJK-LMNPQ-RSTUV`, to set a new password without an administrator. It is shown only once: ainonyproxy keeps only its fingerprint (SHA-256), so nobody can show it again. Copy it or write it down, and keep it in a safe place.

| When | Who sees the code |
|---|---|
| You create your account at `/auth/register/` | You |
| An administrator creates your user in **Users** | The administrator, who hands it over to you |
| You press **Generate a new recovery code** in **Account** (it asks for your current password) | You. The previous code stops working. |
| You use it at `/auth/recover/` | You get a new one: each code works only once |

The administrator created by the installer, and the users created from the terminal, start without a code: generate one in **Account**.

### Forgetting your password

Open `/auth/recover/` (link "Forgot your password?" of the login) and type your user, your recovery code (with or without hyphens, in upper or lower case) and the new password twice. The password changes, every session of the account is closed and the page shows your new recovery code. Wrong attempts count as failed logins: after 5 from the same address, wait 15 minutes.

Without a recovery code, an administrator can give you a new password in **Users**, and root can do it from the server terminal (next section).

### Resetting a password from the terminal

If nobody can log in any more, set a new password from the server as root:

```bash
printf '%s\n' 'TheNewPassword' | AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/ainonyproxy.py --set-user admin --role admin --password-stdin
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/db
```

The same command creates the user when it does not exist. `--list-users` lists the users. Passwords need at least 8 characters.

## The admin dashboard

`/admin/dashboard/` opens the **Overview** tab. Each tab has its own address, so you can bookmark it or open it directly.

| Tab | Address | What it has |
|---|---|---|
| Overview | `/admin/dashboard/overview/` | Total requests, requests with masked PII, average scan time, requests of the last hour, the PII entity types detected most, and the latest 50 requests. It refreshes every 5 seconds. Click a request to see its masked content (when it is logged). |
| Users | `/admin/dashboard/users/` | Open or close the registration at `/auth/register/`. Create users (name, password, role): the recovery code of the new user is shown once, so you can hand it over. Give users a new password, delete them. The last administrator and your own user cannot be deleted. |
| Account | `/admin/dashboard/account/` | Your data, the form to change your password (changing it closes your other sessions) and the one to generate a new recovery code. |
| Help | `/admin/dashboard/help/` | A summary of how to use ainonyproxy. |

The sidebar also has a link to the user dashboard, the button to log out, the theme switch (see [Light and dark theme](#light-and-dark-theme)) and the language selector (en-GB, en-US, es-AR, es-ES, fr-FR). Every time is shown in UTC with the format `2026/10/29@13:59:59.723`.

## The user dashboard

`/user/dashboard/` opens the **API** tab.

| Tab | Address | What it has |
|---|---|---|
| API | `/user/dashboard/api/` | The base URL, an example with `curl` and the table of available providers with their endpoint. |
| Account | `/user/dashboard/account/` | Your data, the form to change your password and the one to generate a new recovery code. |
| Help | `/user/dashboard/help/` | A summary of how to use ainonyproxy. |

## Light and dark theme

Every page (login, registration, password recovery and both dashboards) has a light and a dark theme. The theme switch is at the bottom of the sidebar of the dashboards, and under the card of the login pages. It has three buttons:

| Button | Theme |
|---|---|
| System (screen icon) | The theme of your operating system. It is the default, and the page changes by itself when the system changes. |
| Light (sun icon) | Always light. |
| Dark (moon icon) | Always dark. |

The choice is remembered in this browser (`localStorage`, key `ainonyproxy_theme`) and applies to every page of ainonyproxy open in it.

## Sending requests through ainonyproxy

Point your application to `https://localhost:11443/api/ai/{provider}` instead of the URL of the provider, and send the same OpenAI-style chat request:

```bash
curl -k https://localhost:11443/api/ai/openai \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-5-nano",
    "messages": [
      {"role": "user", "content": "Write an e-mail to John Smith, his address is john@example.com"}
    ]
  }'
```

The provider receives `Write an e-mail to <PERSON_1>, his address is <EMAIL_ADDRESS_1>` and your application receives the answer with the real name and address back in place.

- `-k` tells curl to accept the self-signed certificate. Other clients have a similar option, or you can install the certificate as trusted.
- Add `"stream": true` for streaming (Server-Sent Events, as OpenAI).
- `messages` accepts the roles `system`, `user` and `assistant`, with text content.
- The other fields (`temperature`, `max_tokens`, `stop`...) are passed to the provider. For Anthropic they are converted to its format.
- `GET /api/ai/` lists the providers with their full URL.

### Response headers

| Header | Meaning |
|---|---|
| `X-Ainonyproxy-Provider` | Provider used |
| `X-Ainonyproxy-PII-Detected` | `true` when the last user message had PII |
| `X-Ainonyproxy-PII-Masked` | `true` when the conversation was masked |
| `X-Ainonyproxy-Language` | Language used for the detection |
| `X-Ainonyproxy-Language-Fallback` | `true` when the detected language was not configured and the fallback was used |
| `X-Request-ID` | Identifier of the request (yours, if you sent one) |

### Errors

| Code | When |
|---|---|
| `400` | The body is not a valid chat request |
| `404` | The provider does not exist |
| `502` | The provider answered with an error, or could not be reached |
| `503` | PII detection is not available |

## Providers and API keys

The providers are in `/opt/ainonyproxy/config/api_urls.json`:

```json
{
  "openai": { "url": "https://api.openai.com/v1/chat/completions" },
  "anthropic": { "url": "https://api.anthropic.com/v1/messages" },
  "ollama": { "url": "http://localhost:11434/v1/chat/completions" }
}
```

Each entry can also have `"format"` (`openai` or `anthropic`; it is deduced from the URL when it is missing) and `"model"` (a model that is always used, whatever the client asks for). The name of the entry is the name in the URL: `/api/ai/openai`.

The keys are in `/opt/ainonyproxy/config/api_keys.json`, apart from the rest so that this file alone has the secrets:

```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-...",
  "ollama": ""
}
```

Local providers (`localhost`, `10.x`, `172.16-31.x`, `192.168.x`) can have an empty key. Values can use environment variables: `"${OPENAI_API_KEY}"`.

After editing either file, keep the owner and restart:

```bash
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/config/*.json
chmod 600 /opt/ainonyproxy/config/*.json
systemctl restart ainonyproxy        # Debian
rc-service ainonyproxy restart       # Alpine
```

Included by default: `anthropic`, `deepseek`, `gemini`, `kimi`, `llamacpp`, `ollama`, `openai`, `openrouter`, `vllm` and `zai`. `gemini` is declared but is sent as OpenAI-compatible, which the native Gemini API does not understand; and `llamacpp` points to `/completion`, which is not a chat endpoint. Use the OpenAI-compatible URL of those servers if you need them.

## PII detection

It is configured in `/opt/ainonyproxy/config/pii_detection.json`:

| Key | Meaning | Default |
|---|---|---|
| `languages` | Languages to detect (spaCy codes: `en`, `es`, `fr`, `de`, `it`, `pt`, `ca`...) | `["es", "en"]` |
| `fallback_language` | Language used when the detected one is not in the list | `es` |
| `score_threshold` | Minimum confidence (0 to 1) to treat something as PII. Lower finds more, also more false positives. | `0.5` |
| `entities` | Presidio entity types to look for | A wide list (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN_CODE`, `ES_NIF`...) |

Each language needs its spaCy model. After adding one, install its model and restart:

```bash
/opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/presidio/setup.py --languages fr
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/venv
systemctl restart ainonyproxy
```

Or run the installer with `--update`, which installs the models of every configured language. ainonyproxy refuses to start when a configured language has no model, so that it never lets personal data through by mistake.

Only the last user message decides whether a conversation has PII. When it has, every user and assistant message is masked, and the same value always gets the same marker.

## What is written to the database

Every request is logged in `/opt/ainonyproxy/db/ainonyproxy.db`: time, provider, model, whether it had PII, entity types, language, times and tokens. Whether the texts are logged too depends on `config.json`:

| Key | What it controls | Default |
|---|---|---|
| `logging.log_content` | Original request and answer to the client (with the real personal data) | `false` |
| `logging.log_masked_content` | Masked request and answer of the provider (with markers) | `true` |
| `logging.retention_days` | Days a request is kept; `0` keeps them for ever | `30` |

With the defaults, the database never holds the personal data itself.

The same database holds the dashboard users (only the fingerprints of their passwords and recovery codes, never the values), their sessions (only the fingerprint of each token) and the settings that an administrator changes from the dashboard (table `app_settings`, such as whether the registration is open).

## Configuration reference

`/opt/ainonyproxy/config/config.json`:

| Key | Meaning | Default |
|---|---|---|
| `mode` | Only `mask` exists | `mask` |
| `server.host` | Address to listen on | `0.0.0.0` |
| `server.port` | HTTP port (it only redirects to HTTPS) | `11080` |
| `server.ssl_port` | HTTPS port | `11443` |
| `server.proxy_protocol` | Expect the PROXY protocol on HTTPS (for an HAProxy in front with `send-proxy`) | `false` |
| `server.ssl.enabled` / `certfile` / `keyfile` | Certificate of your own, used when there is no Let's Encrypt certificate in the certificates folder | `false` |
| `masking.show_markers` | Put `marker_text` in front of every unmasked value in the answers | `false` |
| `masking.marker_text` | Text used by `show_markers` | `[protected]` |
| `logging.*` | See [What is written to the database](#what-is-written-to-the-database) | |
| `logging.database` | Path of the SQLite database | `/opt/ainonyproxy/db/ainonyproxy.db` |
| `dashboard.enabled` | Reserved; the dashboard is always available | `true` |
| `dashboard.session_hours` | Duration of a dashboard session | `12` |
| `ui.default_language` | Interface language for whoever has not chosen one | `en-US` |

Restart the service after changing it.

## Files and folders

```
/opt/ainonyproxy/
├── webapp/          Code (backend/ and frontend/). Replaced by every update.
├── venv/            Python virtual environment
├── config/          config.json, api_urls.json, api_keys.json, api_models.json, pii_detection.json
├── db/              ainonyproxy.db (requests, users, sessions, settings)
├── certificates/    fullchain.pem + privkey.pem (Let's Encrypt) or selfsigned-*.pem
├── logs/            Output of the process when it does not run under systemd
└── run/             PID file when it runs without a service manager
```

Everything belongs to the user `ainonyproxy`. `config/`, `db/` and `certificates/` can only be read by it (and by root).

## Certificates

Without anything else, ainonyproxy serves HTTPS with a self-signed certificate (`/opt/ainonyproxy/certificates/selfsigned-fullchain.pem`), valid for `localhost`, `127.0.0.1` and the name of the machine.

To use a Let's Encrypt certificate, copy its two files to the certificates folder with these names, and restart:

```bash
cp /etc/letsencrypt/live/your.domain/fullchain.pem /opt/ainonyproxy/certificates/fullchain.pem
cp /etc/letsencrypt/live/your.domain/privkey.pem /opt/ainonyproxy/certificates/privkey.pem
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/certificates/*.pem
chmod 600 /opt/ainonyproxy/certificates/privkey.pem
systemctl restart ainonyproxy
```

They take priority over everything else. Repeat the copy after every renewal.

## Running it without the service

`deploy/run.sh` (in a copy of the repository) creates the virtual environment, installs what is missing and starts ainonyproxy in the foreground, showing everything it does. Stop it with `Ctrl+C`.

```bash
bash deploy/run.sh                                   # as root, uses /opt/ainonyproxy
AINONYPROXY_HOME="$PWD/_/temp/home" bash deploy/run.sh   # as any user, in a folder of your own
```

If the installed service is running, stop it first: both use the same ports (ainonyproxy stops whatever is still listening on them before starting).

When there are no users yet (it was never installed), the first start creates `admin` and prints its password once in the terminal.

## Looking inside the database

```bash
AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/view_database.py
```

A menu shows the users, the sessions, the latest requests, the detail of a request, the masked contents and general statistics.

## Troubleshooting

| What happens | What to do |
|---|---|
| The service does not start | `journalctl -u ainonyproxy -n 100 --no-pager` (Debian) or `/opt/ainonyproxy/logs/ainonyproxy.log` (Alpine and containers). |
| "Missing spaCy models" | Install the models of the configured languages (see [PII detection](#pii-detection)) or run the installer with `--update`. |
| A provider answers 502 | Check its URL in `api_urls.json` and its key in `api_keys.json`. The detail of the error is in the answer. |
| "Remote providers without an API key" at startup | Add their keys to `api_keys.json`, or ignore it for the providers you do not use. |
| The browser warns about the certificate | Expected with the self-signed certificate. See [Certificates](#certificates). |
| "Too many failed attempts" | Wait 15 minutes, or restart the service. |
| Nobody remembers the admin password | See [Resetting a password from the terminal](#resetting-a-password-from-the-terminal). |
| "The registration is closed" | An administrator opens it in **Users → Registration**, or creates the account for you. |
| Lost the recovery code | While you can still log in, generate a new one in **Account → Recovery code**. If you cannot log in, an administrator gives you a new password in **Users**. |
| The first start takes long | Loading the spaCy models takes from several seconds to a minute; the installer waits for up to 3 minutes. |

## Uninstalling

As root:

```bash
systemctl disable --now ainonyproxy && rm -f /etc/systemd/system/ainonyproxy.service && systemctl daemon-reload   # Debian
rc-service ainonyproxy stop; rc-update del ainonyproxy default; rm -f /etc/init.d/ainonyproxy                     # Alpine
rm -rf /opt/ainonyproxy
userdel ainonyproxy     # Debian (on Alpine: deluser ainonyproxy)
rm -f /root/webapp-credentials.txt /root/webapp-install.log
```
