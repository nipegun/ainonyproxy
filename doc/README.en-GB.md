# ainonyproxy

This README is also available in:\
en-GB, [en-US](../README.md), [es-AR](README.es-AR.md), [es-ES](README.es-ES.md), [fr-FR](README.fr-FR.md)

## What is it

A privacy proxy for AI chat models (LLMs) that runs on your own GNU/Linux computer (Debian or Alpine).

Your applications send their chat requests to ainonyproxy instead of the AI provider, and ainonyproxy:

- Finds the personal data in the messages (names, e-mails, phones, IBANs, addresses, ID numbers...).
- Replaces it with markers such as `<PERSON_1>` before anything leaves your computer.
- Sends the masked conversation to OpenAI, Anthropic, DeepSeek, Ollama, OpenRouter, vLLM, etc.
- Puts the real data back into the answer.

It speaks the OpenAI chat API (with streaming), and it has a web dashboard with statistics, request logs and users.

## Screenshots

![ainonyproxy dashboard](https://raw.githubusercontent.com/nipegun/ainonyproxy/main/doc/screenshot.png)

## Install

Run it as `root`.

**Debian**:

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh \
  | bash -s -- --install
```

**Alpine Linux**:

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh \
  | bash -s -- --install
```

Then open `https://localhost:11443/` and log in with the password saved in `/root/webapp-credentials.txt`.

## Read the documentation

Explore:

- [doc/MANUAL.en-GB.md](MANUAL.en-GB.md) to learn how to install it, set it up and use it.
- [doc/CODE.en-GB.md](CODE.en-GB.md) to understand how it is built (for developers and for AI models).

## Sponsor this project

- **[Hire me](mailto:nipegun@gmail.com?subject=I%20want%20to%20hire%20you%21)** to add new features.
- **GitHub Sponsors.** You can also support the project financially on GitHub: [github.com/sponsors/nipegun](https://github.com/sponsors/nipegun).
