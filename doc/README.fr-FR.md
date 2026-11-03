# ainonyproxy

Ce README est également disponible en :\
[en-GB](README.en-GB.md), [en-US](../README.md), [es-AR](README.es-AR.md), [es-ES](README.es-ES.md), fr-FR

## Qu'est-ce que c'est

Un proxy de confidentialité pour les modèles de chat IA (LLM) qui s'exécute sur votre propre ordinateur GNU/Linux (Debian ou Alpine).

Vos applications envoient leurs requêtes de chat à ainonyproxy plutôt qu'au fournisseur d'IA, et ainonyproxy :

- Repère les données personnelles dans les messages (noms, e-mails, téléphones, IBAN, adresses, numéros d'identité...).
- Les remplace par des marqueurs tels que `<PERSON_1>` avant que quoi que ce soit ne quitte votre ordinateur.
- Envoie la conversation masquée à OpenAI, Anthropic, DeepSeek, Ollama, OpenRouter, vLLM, etc.
- Remet les données réelles dans la réponse.

Il parle l'API de chat d'OpenAI (avec streaming) et dispose d'un tableau de bord web avec des statistiques, des journaux de requêtes et des utilisateurs.

## Captures d'écran

![Tableau de bord d'ainonyproxy](https://raw.githubusercontent.com/nipegun/ainonyproxy/main/doc/screenshot.png)

## Installation

Exécutez-le en tant que `root`.

**Debian** :

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh \
  | bash -s -- --install
```

**Alpine Linux** :

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh \
  | bash -s -- --install
```

Ouvrez ensuite `https://localhost:11443/` et connectez-vous avec le mot de passe enregistré dans `/root/webapp-credentials.txt`.

## Lire la documentation

Explorez :

- [doc/MANUAL.fr-FR.md](MANUAL.fr-FR.md) pour apprendre à l'installer, à le configurer et à l'utiliser.
- [doc/CODE.fr-FR.md](CODE.fr-FR.md) pour comprendre comment il est construit (pour les développeurs et pour les modèles d'IA).

## Soutenir ce projet

- **[Engagez-moi](mailto:nipegun@gmail.com?subject=I%20want%20to%20hire%20you%21)** pour ajouter de nouvelles fonctionnalités.
- **GitHub Sponsors.** Vous pouvez également soutenir financièrement le projet sur GitHub : [github.com/sponsors/nipegun](https://github.com/sponsors/nipegun).
