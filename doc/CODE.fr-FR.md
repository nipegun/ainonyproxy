# ainonyproxy - CODE

Ce CODE est également disponible en :\
[en-GB](CODE.en-GB.md), [en-US](CODE.md), [es-AR](CODE.es-AR.md), [es-ES](CODE.es-ES.md), fr-FR

Référence technique d'ainonyproxy, pour les développeurs et pour les modèles d'IA. Elle est conçue pour être lue de façon chirurgicale : allez directement à la section dont vous avez besoin, ne la lisez pas de bout en bout.

## Index

1. [Architecture et décisions de conception](#1-architecture-et-décisions-de-conception)
2. [Carte des modules](#2-carte-des-modules)
3. [Index des symboles clés](#3-index-des-symboles-clés)
4. [Flux principaux](#4-flux-principaux)
5. [Points d'entrée et carte des routes](#5-points-dentrée-et-carte-des-routes)
6. [Analyse d'impact](#6-analyse-dimpact)
7. [Points d'extension](#7-points-dextension)

---

## 1. Architecture et décisions de conception

### Ce que c'est

ainonyproxy est une application FastAPI qui s'intercale entre un client de chat et un fournisseur de LLM. Pour chaque requête, elle détecte les données personnelles (PII) avec un Presidio intégré, les remplace par des marqueurs tels que `<PERSON_1>`, envoie la conversation masquée au fournisseur, puis remet les valeurs réelles dans la réponse avant de la renvoyer. Les requêtes, les statistiques et les utilisateurs du tableau de bord résident dans une seule base de données SQLite.

### Un processus, deux écouteurs

Le processus écoute toujours sur deux ports :

| Port | Ce qui répond | Pourquoi |
|---|---|---|
| `11080` (HTTP) | Une minuscule application FastAPI construite par `fCreateRedirectApp` | Elle répond uniquement par un `308 Permanent Redirect` vers le même chemin en HTTPS. Le 308 (et non le 301) conserve la méthode et le corps, de sorte qu'un client qui envoie un POST en HTTP par erreur n'est pas transformé en GET. |
| `11443` (HTTPS) | L'application réelle, `vApp` | Tout : API, tableaux de bord, documentation. |

HTTPS n'est jamais facultatif. Le certificat est choisi dans cet ordre : les fichiers Let's Encrypt dans `/opt/ainonyproxy/certificates/` (`fullchain.pem` + `privkey.pem`), puis les fichiers nommés dans `config.json` (`server.ssl`), puis un certificat autosigné (`selfsigned-fullchain.pem` + `selfsigned-privkey.pem`) que l'installateur, ou l'application elle-même avec `openssl`, crée lorsqu'il manque.

Avec `server.proxy_protocol: true`, les deux écouteurs s'exécutent sous Hypercorn, qui comprend le protocole PROXY qu'HAProxy envoie avec `send-proxy`. Sinon, les deux s'exécutent sous Uvicorn dans la même boucle d'événements.

Le logiciel est conçu pour être utilisé depuis le même ordinateur que celui sur lequel il s'exécute : il n'y a donc aucune configuration de proxy à choisir.

### Tout ce que l'application stocke se trouve dans `/opt/ainonyproxy/`

| Chemin | Contenu | Mode |
|---|---|---|
| `/opt/ainonyproxy/webapp/` | Code : `backend/` et `frontend/` copiés depuis le dépôt | propriétaire `ainonyproxy` |
| `/opt/ainonyproxy/venv/` | Environnement virtuel Python | propriétaire `ainonyproxy` |
| `/opt/ainonyproxy/config/` | `config.json`, `api_urls.json`, `api_keys.json`, `api_models.json`, `pii_detection.json` | `700`, fichiers `600` |
| `/opt/ainonyproxy/db/ainonyproxy.db` | SQLite : `request_logs`, `users`, `user_sessions`, `app_settings` | `700`, fichier `600` |
| `/opt/ainonyproxy/certificates/` | Certificat Let's Encrypt ou autosigné | `700`, clés `600` |
| `/opt/ainonyproxy/logs/` | Sortie du processus lorsqu'il ne s'exécute pas sous systemd | `750` |
| `/opt/ainonyproxy/run/` | Fichier PID lorsqu'il s'exécute sans gestionnaire de services | `750` |

`config.py` construit chaque chemin à partir de `cHomeDir`, qui vaut `/opt/ainonyproxy` sauf si la variable d'environnement `AINONYPROXY_HOME` indique autre chose (utilisée uniquement pour exécuter le code depuis une copie de travail). La configuration du dépôt (`backend/config-defaults/`) n'est qu'un modèle : l'installateur copie chaque fichier dans `/opt/ainonyproxy/config/` lorsqu'il n'existe pas encore, de sorte qu'une mise à jour n'écrase jamais ce que l'utilisateur a modifié.

Le processus s'exécute sous l'utilisateur système `ainonyproxy` (sans mot de passe, sans shell de connexion), le seul, à part root, qui puisse lire la configuration, la base de données et les clés.

### Configuration répartie en plusieurs fichiers

`fLoadConfig` lit `config.json` puis écrase deux sections avec leurs propres fichiers : `providers` est construit à partir de `api_urls.json` (URL, format, modèle par défaut) plus `api_keys.json` (clés), et `pii_detection` provient de `pii_detection.json`. Les clés sont séparées afin que le fichier contenant les secrets puisse être en `600` et ne soit jamais affiché ni copié avec le reste. Chaque chaîne peut utiliser `${VAR}` ou `${VAR:-default}`, remplacés à partir de l'environnement.

Lorsque des clés manquent, `fEnsureApiKeys` ne les demande que s'il y a un terminal. Sous systemd ou OpenRC il n'y en a pas : la fonction écrit donc des entrées vides et continue, car un service ne doit jamais attendre une saisie.

### Détection des PII : seul le dernier message de l'utilisateur décide

`PiiDetector.mAnalyzeMessages` n'analyse que le dernier message `user` ayant du contenu. S'il ne contient aucune PII, la conversation part telle quelle. S'il en contient, `mAnalyzeAllMessages` analyse chaque message `user` et `assistant` (avec la langue détectée pour le dernier) et `fMaskMessages` les masque tous avec un seul `MaskingContext` partagé, de sorte que la même valeur reçoit le même marqueur partout dans la conversation. Ainsi, le coût du cas courant (sans PII) se limite à une seule analyse.

La détection de la langue (`langdetect`) sert uniquement à choisir le pipeline Presidio à utiliser. Si la langue détectée n'est pas configurée, la langue de repli est utilisée et la requête est signalée (`X-Ainonyproxy-Language-Fallback`).

Au démarrage, l'application refuse de s'exécuter si une langue configurée n'a aucun modèle spaCy installé : détecter les PII avec le mauvais modèle laisserait passer des données en silence.

### Démasquage

`fUnmaskText` remplace les marqueurs du plus long au plus court, de sorte que `<PERSON_10>` n'est jamais cassé par `<PERSON_1>`. En streaming, `fUnmaskStreamFragment` conserve dans un tampon tout ce qui suit un `<` sans `>` correspondant pour l'instant, car un marqueur peut arriver coupé en deux fragments ; `fFlushStreamBuffer` le vide à la fin.

### Ce qui est écrit dans la base de données

`fCreateLogData` obéit à deux interrupteurs de `config.json` (`logging`) :

| Interrupteur | Colonnes qu'il contrôle | Par défaut |
|---|---|---|
| `log_content` | `original_content`, `client_response` (textes réels, non masqués) | `false` |
| `log_masked_content` | `masked_content`, `provider_response` (textes masqués) | `true` |

Ainsi, par défaut, la base de données ne contient jamais les données personnelles elles-mêmes. `fPeriodicCleanupTask` supprime les requêtes plus anciennes que `retention_days` une fois au démarrage, puis toutes les 24 heures.

### Dates

Le format natif est le format de stockage des règles : UTC, `2026-10-29@13-59-59.723`. C'est ce que produit `services/dates.py` (`fNowStorage`) et ce que SQLite produit lui-même comme valeur par défaut de colonne (`cSqliteStorageNow`). Ce format se trie comme du texte ; « la dernière heure » et « plus ancien que 30 jours » sont donc de simples comparaisons de chaînes. L'interface affiche `2026/10/29@13:59:59.723` (`fStorageToDisplay` en Python, `fStorageDateToDisplay` en JavaScript). Tout autre format doit être dérivé du format natif au moyen d'une fonction, jamais écrit à la main.

### Utilisateurs du tableau de bord et sessions

Deux rôles : `admin` et `user`. Les mots de passe sont stockés en PBKDF2-SHA256 (600 000 itérations, sel aléatoire). Une connexion crée un jeton aléatoire : le navigateur le conserve dans le cookie `ainonyproxy_session` (`Secure`, `HttpOnly`, `SameSite=Strict`) et la base de données ne conserve que son SHA-256 (`user_sessions.token_hash`), de sorte qu'une copie de la base de données ne donne pas de sessions valides. Modifier un mot de passe ferme les autres sessions de ce compte ; lorsqu'un administrateur définit un mot de passe pour quelqu'un, toutes les sessions de cette personne sont fermées. Le dernier administrateur ne peut pas être supprimé.

`/api/auth/login` autorise 5 tentatives échouées par adresse cliente toutes les 15 minutes (en mémoire). Une connexion pour un utilisateur inexistant effectue le même travail PBKDF2 qu'une connexion réelle, de sorte que le temps de réponse ne révèle pas quels utilisateurs existent.

Des comptes peuvent aussi être créés sur `/auth/register/` tant que le réglage `registration_open` (table `app_settings`, `services/settings.py`) est vrai, ce qui est sa valeur par défaut ; ils reçoivent toujours le rôle `user`. `/api/auth/register` autorise 5 comptes par adresse cliente toutes les heures (en mémoire).

Chaque compte peut avoir un code de récupération (`fGenerateRecoveryCode` : 20 caractères d'un alphabet de 32, 100 bits aléatoires). Comme pour les jetons de session, seul son SHA-256 est stocké (`users.recovery_code_hash`) ; il est comparé en temps constant et `UserStore.mRecoverPassword` le consomme : nouveau mot de passe, toutes les sessions fermées, nouveau code renvoyé. `/api/auth/recover` compte ses échecs dans le même frein que la connexion. Un code n'est affiché qu'une seule fois : à l'inscription, à l'administrateur qui crée un utilisateur, quand l'utilisateur en génère un nouveau dans Compte (le mot de passe actuel est demandé) et après une récupération.

Les réglages modifiés depuis le tableau de bord se trouvent dans `app_settings` et non dans `config.json`, de sorte que les enregistrer ne réécrit jamais les fichiers que l'utilisateur modifie à la main (ni leurs références `${VAR}`).

Le tout premier démarrage sans aucun utilisateur (possible uniquement sans passer par l'installateur) crée `admin` avec un mot de passe aléatoire et l'affiche une seule fois.

### Décisions de sécurité

- CORS autorise n'importe quelle origine mais **sans identifiants** : une page web d'un autre site peut appeler l'API d'IA, mais ne peut jamais s'appuyer sur la session de tableau de bord de la personne qui la visite. `SameSite=Strict` empêche de toute façon le cookie de voyager dans les requêtes inter-sites.
- Toute valeur provenant du serveur ou d'un utilisateur est échappée avec `fEscapeHtml` avant d'entrer dans `innerHTML` (le nom de modèle d'une requête était auparavant une faille XSS).
- Le paramètre `next` de la connexion n'accepte que des chemins de ce même site (`fIsSafeNextPath`), de sorte que la connexion ne peut pas servir à rediriger ailleurs.
- Chaque réponse porte `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` et `Referrer-Policy: same-origin`.
- `fFreePort` arrête tout ce qui écoute encore sur 11080 ou 11443 avant de se mettre à l'écoute (une instance précédente restée en place), comme l'exigent les règles.

### Pourquoi les installateurs exécutent leurs étapes dans un nouveau bash

Les règles exigent `set -euo pipefail` et de terminer par `if ! fMain; then ... fi`. Mais une fonction appelée comme condition d'un `if` s'exécute avec `set -e` suspendu, tout comme tout ce qu'elle appelle, même un processus fils en arrière-plan (mesuré avec bash 5.2). `fMain` exporte donc chaque fonction et chaque variable `c*`/`v*` et exécute `fRunSteps` dans un nouveau `bash -c 'set -euo pipefail; ...'`, qui retrouve `set -e` : la première commande qui échoue arrête l'installation, et `if ! fMain` le signale. `deploy/run.sh` fait de même.

### Pourquoi les installateurs peuvent être envoyés de curl à bash

Les installateurs sont conçus pour être exécutés comme `curl -fsSL <URL raw> | bash -s -- --install`, directement depuis le dépôt GitHub, et pour être idempotents : en exécuter un deux fois avec la même option laisse le système dans le même état qu'une seule exécution (chaque étape vérifie avant d'agir : utilisateur existant, fichiers de configuration existants, certificat existant, administrateur existant). Ce qui rend le tube sûr :

- Bash exécute un script reçu par un tube pendant qu'il arrive encore. Le niveau supérieur ne fait que définir des constantes et des fonctions, et la dernière ligne (`if ! fMain "$@"; then ... fi`) les exécute : un téléchargement interrompu à mi-chemin n'exécute donc rien.
- L'entrée standard du bash du tube est le script lui-même. `fRunSteps` s'exécute avec son entrée standard sur `/dev/null`, donc aucune commande (apt, pip, python) ne peut avaler la suite du script. La seule question, `--reinstall` sans `--yes`, lit `/dev/tty`, et sans terminal il s'arrête et demande `--yes`.
- `vScriptPath` (`BASH_SOURCE[0]`) est vide dans un tube, donc `fObtainSourceCode` télécharge `cSourceTarballUrl` (branche `main` de `github.com/nipegun/ainonyproxy`). Exécuté depuis une copie du dépôt, il utilise cette copie.
- Envoyé à `sh` au lieu de `bash`, une vérification POSIX juste après `set -euo pipefail` l'arrête et affiche la bonne ligne de commande.
- L'apt de Debian ne pose jamais de question (`DEBIAN_FRONTEND=noninteractive`, `--force-confdef --force-confold`) et attend jusqu'à 10 minutes que le verrou d'un autre apt soit libéré (`DPkg::Lock::Timeout=600`).
- `fCleanup` ferme le tube vers `tee` et l'attend (5 s au maximum), pour que les dernières lignes ne s'affichent pas après l'invite.

### Langues de l'interface

Les textes se trouvent dans `frontend/lang/<code>.json` (`en-GB`, `en-US`, `es-AR`, `es-ES`, `fr-FR`). `en-US.json` est la source et le balisage porte le texte en-US en secours, de sorte qu'une clé manquante affiche de l'anglais au lieu d'un nom de clé. `/api/languages` les liste triées par code (ce qui correspond à l'ordre alphabétique exigé par les règles), et le choix est mémorisé dans `localStorage` (`ainonyproxy_lang`).

### Thème clair et thème sombre

Chaque page inclut `partials/theme-head.html` dans son `<head>`. Il définit chaque couleur comme une propriété personnalisée CSS trois fois : sombre (`:root`, par défaut), clair selon la préférence du système (`@media (prefers-color-scheme: light)` sauf avec `data-theme="dark"`) et clair choisi (`:root[data-theme="light"]`). Aucune règle des pages n'écrit une couleur directement, sauf les dégradés et halos de la marque, qui fonctionnent dans les deux thèmes. Un petit script en ligne place `data-theme` sur `<html>` à partir de `localStorage` (`ainonyproxy_theme`) avant le premier rendu, de sorte que la page n'affiche jamais un éclair de l'autre thème. Sans choix enregistré il n'y a pas de `data-theme` et la page suit le thème du système, y compris quand il change pendant que la page est ouverte. `partials/theme-script.html` dessine le sélecteur (Système / Clair / Sombre) avec `fRenderThemeSwitch` et enregistre le choix avec `fSetTheme` ; l'événement `storage` le transmet aux autres onglets ouverts.

### Pages sans session

`login.html`, `register.html` et `recover.html` étendent `auth-base.html`, qui contient leurs styles, la ligne des langues, le sélecteur de thème et le script commun (`fTranslateOr`, `fErrorTextFromData`, `fIsSafeRedirect`, `fCopyCode`). Chaque page définit `vPageTitleKey` et `vPageTitleFallback` et remplit les blocs `content` et `scripts`.

---

## 2. Carte des modules

| Module | Chemin | Responsabilité | Dépend de | Utilisé par |
|---|---|---|---|---|
| Point d'entrée | `backend/ainonyproxy.py` | Construit `vApp`, les middlewares, les routeurs, les certificats, les ports, les vérifications au démarrage, la CLI des utilisateurs | `config`, tous les `routes/*`, `services.logger`, `services.users`, `services.port_guard` | systemd/OpenRC, `deploy/run.sh`, installateurs |
| Configuration | `backend/config.py` | Chemins sous `/opt/ainonyproxy/`, modèles Pydantic, chargement et enregistrement des fichiers JSON | `pydantic` | tous |
| Routes IA | `backend/routes/chat.py` | `/api/ai/` (liste) et `/api/ai/{provider}` (chat), démasquage SSE | `services.decision`, `services.masking`, `services.logger`, `services.dates` | `ainonyproxy.py` |
| Statut | `backend/routes/health.py` | `/api/ai/status` | `services.decision` | `ainonyproxy.py`, installateurs (vérification) |
| Info | `backend/routes/info.py` | `/api/ai/info` | `config`, `services.decision`, `services.pii_detector` | `ainonyproxy.py` |
| Routes d'authentification | `backend/routes/auth.py` | Pages `/auth/login/`, `/auth/register/` et `/auth/recover/`, `/api/auth/*`, freins anti-force brute et d'inscription | `services.auth`, `services.users`, `services.settings`, `routes.users` (`fUserErrorToHttp`) | `ainonyproxy.py` |
| Routes du tableau de bord | `backend/routes/dashboard.py` | `/`, `/admin/dashboard/*`, `/user/dashboard/*`, `/api/admin/logs`, `/api/admin/stats`, `/api/languages*` | `services.auth`, `services.logger`, `config` | `ainonyproxy.py` |
| Routes des utilisateurs | `backend/routes/users.py` | `/api/admin/users*`, `/api/admin/registration`, `/api/user/account*` | `services.auth`, `services.users`, `services.settings` | `ainonyproxy.py`, `routes/auth.py` |
| Décision | `backend/services/decision.py` | `Router` : un `LlmClient` par fournisseur, décide s'il faut masquer | `services.pii_detector`, `services.masking`, `services.llm_client` | `routes/chat.py`, `routes/health.py`, `routes/info.py` |
| Détecteur de PII | `backend/services/pii_detector.py` | Analyse les messages, valide les modèles spaCy | `presidio.analyzer`, `services.language_detector` | `services.decision`, `ainonyproxy.py`, `routes/info.py` |
| Détecteur de langue | `backend/services/language_detector.py` | `langdetect` + langue de repli | `config` | `services.pii_detector` |
| Masquage | `backend/services/masking.py` | Masquage, démasquage, tampon de streaming | `services.pii_detector` (types) | `services.decision`, `routes/chat.py` |
| Client LLM | `backend/services/llm_client.py` | HTTP vers les API compatibles OpenAI et Anthropic, streaming | `httpx` | `services.decision` |
| Journal des requêtes | `backend/services/logger.py` | `request_logs`, statistiques, nettoyage ; `fOpenDatabase` | `config`, `services.dates` | `routes/chat.py`, `routes/dashboard.py`, `services.users`, `ainonyproxy.py` |
| Utilisateurs | `backend/services/users.py` | `users`, `user_sessions`, hachage des mots de passe, codes de récupération | `services.logger` (`fOpenDatabase`), `services.dates` | `services.auth`, `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Réglages | `backend/services/settings.py` | `app_settings` : réglages modifiés depuis le tableau de bord (`registration_open`) | `services.logger` (`fOpenDatabase`), `services.dates` | `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Utilitaires d'authentification | `backend/services/auth.py` | Cookie de session, utilisateur courant, gardes, redirection vers la connexion | `services.users`, `config` | `routes/auth.py`, `routes/dashboard.py`, `routes/users.py` |
| Dates | `backend/services/dates.py` | Formats de date de stockage et d'affichage | - | `logger`, `users`, `chat`, `view_database.py` |
| Garde de ports | `backend/services/port_guard.py` | Libère un port TCP via `/proc` | - | `ainonyproxy.py` |
| Enveloppe Presidio | `backend/presidio/analyzer.py` | `AnalyzerEngine` avec un modèle spaCy par langue | `presidio_analyzer`, `config` | `services.pii_detector` |
| Modèles spaCy | `backend/presidio/setup.py` | Installe les modèles spaCy | `pip` | installateurs, `deploy/run.sh` |
| Visionneuse de la base de données | `backend/view_database.py` | Visionneuse interactive de la base de données dans le terminal | `config`, `services.dates` | les humains |
| Page du tableau de bord | `frontend/templates/dashboard.html` | Les deux tableaux de bord (Jinja2 + JavaScript natif) | `/api/*` | `routes/dashboard.py` |
| Pages sans session | `frontend/templates/auth-base.html` + `login.html`, `register.html`, `recover.html` | Formulaires de connexion, d'inscription et de récupération du mot de passe | `/api/auth/*`, `/api/languages*` | `routes/auth.py` |
| Thème | `frontend/templates/partials/theme-head.html`, `partials/theme-script.html` | Couleurs des deux thèmes et sélecteur de thème | - | toutes les pages |
| Textes | `frontend/lang/*.json` | Traductions de l'interface | - | toutes les pages |
| Installateurs | `deploy/install-update-reinstall-{debian,alpine}.sh` | Installation, mise à jour, réinstallation | dépôt ou archive tar de GitHub | root |
| Lanceur manuel | `deploy/run.sh` | venv, dépendances, valeurs par défaut, modèles, démarrage au premier plan | `backend/` | les humains |

---

## 3. Index des symboles clés

| Symbole | Fichier:ligne | Ce qu'il fait |
|---|---|---|
| `vApp` | `backend/ainonyproxy.py:288` | L'application FastAPI (documentation dans `/api/doc/`) |
| `fMain` | `backend/ainonyproxy.py:404` | Point d'entrée : CLI ou certificats + ports + serveurs |
| `fRunCommandLine` | `backend/ainonyproxy.py:366` | `--user-exists`, `--list-users`, `--set-user` |
| `fLifespan` | `backend/ainonyproxy.py:242` | Vérifications au démarrage, premier administrateur, bannière, tâche de nettoyage |
| `fValidateStartup` | `backend/ainonyproxy.py:120` | Initialise Presidio et s'arrête si des modèles manquent |
| `fEnsureSelfSignedCertificate` | `backend/ainonyproxy.py:54` | Crée le certificat autosigné avec `openssl` |
| `fCreateRedirectApp` | `backend/ainonyproxy.py:87` | Application HTTP qui répond 308 vers HTTPS |
| `fRequestIdMiddleware` | `backend/ainonyproxy.py:312` | `X-Request-ID` et en-têtes de sécurité |
| `cHomeDir` | `backend/config.py:20` | `/opt/ainonyproxy` (ou `AINONYPROXY_HOME`) |
| `AppConfig` | `backend/config.py:111` | Modèle Pydantic racine de la configuration |
| `fLoadConfig` | `backend/config.py:341` | Lit `config.json` + `api_urls.json` + `api_keys.json` + `pii_detection.json` |
| `fGetConfig` | `backend/config.py:407` | Singleton de la configuration |
| `fEnsureApiKeys` | `backend/config.py:263` | Demande les clés manquantes uniquement s'il y a un terminal |
| `fChatCompletions` | `backend/routes/chat.py:127` | `POST /api/ai/{provider}` : détecter, masquer, appeler, démasquer, journaliser |
| `fCreateLogData` | `backend/routes/chat.py:56` | Construit la ligne de journal, en respectant `log_content` / `log_masked_content` |
| `fCreateUnmaskedStream` | `backend/routes/chat.py:261` | Démasque un flux SSE |
| `fListProviders` | `backend/routes/chat.py:100` | `GET /api/ai/` |
| `Router.mDecide` | `backend/services/decision.py:55` | Analyse + décision de masquage pour une conversation |
| `PiiDetector.mAnalyzeMessages` | `backend/services/pii_detector.py:78` | Analyse le dernier message de l'utilisateur |
| `PiiDetector.mAnalyzeAllMessages` | `backend/services/pii_detector.py:123` | Analyse chaque message de l'utilisateur et de l'assistant |
| `PiiDetector.mValidateLanguages` | `backend/services/pii_detector.py:222` | Quelles langues configurées disposent de leur modèle |
| `fMask` | `backend/services/masking.py:38` | Remplace les entités par des marqueurs |
| `fUnmaskText` | `backend/services/masking.py:87` | Remet les valeurs d'origine |
| `fUnmaskStreamFragment` | `backend/services/masking.py:126` | Démasquage en streaming avec un tampon |
| `LlmClient.mCompleteChat` | `backend/services/llm_client.py:198` | Envoie la requête (compatible OpenAI ou Anthropic) |
| `RequestLogger` | `backend/services/logger.py:75` | Table `request_logs`, statistiques, nettoyage |
| `fOpenDatabase` | `backend/services/logger.py:49` | Ouvre SQLite en créant son dossier avec le mode 700 |
| `UserStore` | `backend/services/users.py:106` | Utilisateurs et sessions |
| `UserStore.mAuthenticate` | `backend/services/users.py:252` | Vérifie les identifiants en temps constant |
| `UserStore.mCreateSession` | `backend/services/users.py:331` | Nouveau jeton de session (seul son hachage est stocké) |
| `fHashPassword` | `backend/services/users.py:50` | PBKDF2-SHA256 |
| `UserStore.mNewRecoveryCode` | `backend/services/users.py:273` | Nouveau code de récupération pour un utilisateur (seul son SHA-256 est stocké) |
| `UserStore.mRecoverPassword` | `backend/services/users.py:288` | Consomme un code de récupération : nouveau mot de passe, sessions fermées, nouveau code |
| `fGenerateRecoveryCode` | `backend/services/users.py:73` | `XXXXX-XXXXX-XXXXX-XXXXX`, 100 bits aléatoires |
| `SettingsStore` | `backend/services/settings.py:29` | Table `app_settings` (réglages modifiés depuis le tableau de bord) |
| `dSettingDefaults` | `backend/services/settings.py:24` | Valeur de chaque réglage tant que personne ne l'a modifié |
| `fGetCurrentUser` | `backend/services/auth.py:27` | Utilisateur du cookie de session |
| `fRequireApiAdmin` | `backend/services/auth.py:70` | Garde 401/403 pour `/api/admin/*` |
| `fLoginRedirect` | `backend/services/auth.py:54` | 303 vers `/auth/login/?next=...` |
| `fIsSafeNextPath` | `backend/services/auth.py:40` | Uniquement des destinations du même site après la connexion |
| `fApiLogin` | `backend/routes/auth.py:137` | `POST /api/auth/login` (frein anti-force brute) |
| `fApiRegister` | `backend/routes/auth.py:157` | `POST /api/auth/register` (ouvert ?, frein, utilisateur, code de récupération, session) |
| `fApiRecover` | `backend/routes/auth.py:188` | `POST /api/auth/recover` (même frein anti-force brute que la connexion) |
| `fApiNewRecoveryCode` | `backend/routes/users.py:115` | `POST /api/user/account/recovery-code` |
| `fApiSetRegistration` | `backend/routes/users.py:95` | `PUT /api/admin/registration` |
| `fAdminDashboardTab` | `backend/routes/dashboard.py:75` | Affiche `/admin/dashboard/<tab>/` |
| `fUserDashboardTab` | `backend/routes/dashboard.py:95` | Affiche `/user/dashboard/<tab>/` |
| `aAdminTabs` / `aUserTabs` | `backend/routes/dashboard.py:35` | Onglets de chaque tableau de bord (le premier est celui par défaut) |
| `fNowStorage` | `backend/services/dates.py:31` | Maintenant, au format de stockage |
| `fStorageToDisplay` | `backend/services/dates.py:56` | Du format de stockage au format d'affichage |
| `fFreePort` | `backend/services/port_guard.py:63` | Arrête tout ce qui écoute sur un port |
| `PiiAnalyzer.mInitialize` | `backend/presidio/analyzer.py:63` | Construit le moteur Presidio avec les modèles spaCy |
| `fEscapeHtml` (JS) | `frontend/templates/dashboard.html`, `auth-base.html` | Échappe chaque valeur dynamique avant `innerHTML` |
| `fStorageDateToDisplay` (JS) | `frontend/templates/dashboard.html` | Format d'affichage des dates dans le navigateur |
| `fSetTheme` / `fRenderThemeSwitch` (JS) | `frontend/templates/partials/theme-script.html` | Enregistre le choix de thème et dessine le sélecteur |
| Jetons du thème (CSS) | `frontend/templates/partials/theme-head.html` | Couleurs des thèmes sombre et clair |
| `fCopyCode` (JS) | `frontend/templates/auth-base.html`, `dashboard.html` | Copie un code de récupération, ou le sélectionne sans accès au presse-papiers |
| `fRunSteps` (bash) | `deploy/install-update-reinstall-*.sh` | Liste ordonnée des étapes d'installation |
| `fMain` (bash) | `deploy/install-update-reinstall-*.sh` | Journalisation + exécute `fRunSteps` dans un nouveau bash |
| `fObtainSourceCode` (bash) | `deploy/install-update-reinstall-*.sh` | Code de la copie locale du dépôt, ou l'archive GitHub quand le script arrive par un tube |
| `fCleanup` (bash) | `deploy/install-update-reinstall-*.sh` | Piège `EXIT` : supprime le code téléchargé et attend `tee` |

---

## 4. Flux principaux

### Requête de chat (`POST /api/ai/{provider}`)

1. `fChatCompletions` (`routes/chat.py`) vérifie le fournisseur avec `Router.mProviderExists` et valide le corps avec `ChatRequestSchema`.
2. `Router.mDecide` → `PiiDetector.mAnalyzeMessages` → `LanguageDetector.mDetect` → `PiiDetector.mDetectPii` → `PiiAnalyzer.mAnalyze` (Presidio).
3. Avec des PII : `Router._mDecideMask` → `PiiDetector.mAnalyzeAllMessages` → `fMaskMessages` → `fMask` pour chaque message.
4. `Router.mGetClient(provider).mCompleteChat(masked request)` → `_mCompleteChatJson` / `_mCompleteChatJsonAnthropic` / `_mCompleteChatStreaming` / `_mCompleteChatStreamingAnthropic`.
5. Réponse JSON : `fUnmaskResponse` → `fLogRequest(fCreateLogData(...))` → `JSONResponse` avec les en-têtes `X-Ainonyproxy-*`.
6. Réponse en streaming : d'abord `fLogRequest` (sans texte de réponse), puis `StreamingResponse(fCreateUnmaskedStream(...))` → `fUnmaskStreamFragment` pour chaque fragment → `fFlushStreamBuffer` à la fin.
7. Erreurs : fournisseur inconnu 404, corps invalide 400, échec de Presidio 503, échec du fournisseur 502.

### Démarrage (`python3 ainonyproxy.py`)

1. `fMain` → `fParseArguments` (les options de la CLI terminent ici) → `fEnsureApiKeys` → `fGetConfig`.
2. Certificat : `fDetectCertificates` → `server.ssl` → `fEnsureSelfSignedCertificate`.
3. `fFreePort(11080)`, `fFreePort(11443)`.
4. Uvicorn (ou Hypercorn avec `proxy_protocol`) démarre `fCreateRedirectApp(11443)` sur 11080 et `vApp` sur 11443.
5. `fLifespan` → `fValidateStartup` (Presidio + modèles, s'arrête si un modèle manque) → `fEnsureAdminUser` → `fPrintStartupBanner` → `fPeriodicCleanupTask`.

### Connexion

1. `GET /admin/dashboard/overview/` sans session → `fAdminDashboardTab` → `fLoginRedirect` → `303 /auth/login/?next=%2Fadmin%2Fdashboard%2Foverview%2F`.
2. `fLoginPage` affiche `login.html` avec `vNext` (uniquement si `fIsSafeNextPath`).
3. Le formulaire appelle `POST /api/auth/login` → `fApiLogin` → `UserStore.mAuthenticate` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON avec `redirect` (le chemin `next`, ou le tableau de bord du rôle).
4. Chaque page ou appel d'API suivant → `fGetCurrentUser` → `UserStore.mGetSessionUser`.

### Inscription

1. `GET /auth/register/` → `fRegisterPage` → `register.html` avec `vRegistrationOpen` (`SettingsStore.mIsRegistrationOpen`). Un utilisateur connecté est renvoyé vers son tableau de bord.
2. Le formulaire appelle `POST /api/auth/register` → `fApiRegister` : 403 `registration_closed`, ou 429 après 5 comptes par adresse et par heure → `UserStore.mCreateUser` (rôle `user`) → `UserStore.mNewRecoveryCode` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON avec `recovery_code` et `redirect`.
3. La page affiche le code une fois ; « Aller à mon tableau de bord » suit `redirect`.

### Récupération du mot de passe

1. `GET /auth/recover/` → `fRecoverPage` → `recover.html`.
2. `POST /api/auth/recover` → `fApiRecover` → frein anti-force brute (`fRecentFailures`) → `UserStore.mRecoverPassword` : valide le nouveau mot de passe, compare en temps constant le SHA-256 du code et, dans un seul `UPDATE ... WHERE recovery_code_hash = <ancien hachage>`, enregistre le nouveau mot de passe et un nouveau code ; supprime ensuite toutes les sessions de l'utilisateur.
3. Utilisateur ou code erroné → 400 `invalid_recovery_code` et un échec de plus. Corrects → JSON avec le nouveau `recovery_code`, affiché une fois.

### Onglet du tableau de bord

`/admin/dashboard/` → 307 vers `/admin/dashboard/overview/` (le premier de `aAdminTabs`). `fAdminDashboardTab` vérifie la session et le rôle, puis affiche `dashboard.html` avec `vRole`, `vTab`, `aTabs`. Le script de la page lit `data-tab` et ne charge que ce dont cet onglet a besoin : `overview` → `/api/admin/stats` + `/api/admin/logs` toutes les 5 s ; `users` → `/api/admin/registration` + `/api/admin/users` ; `account` → `/api/user/account` ; `api` → `/api/ai/` ; `help` → affiché localement.

### Installation (`install-update-reinstall-debian.sh --install`)

`fMain` → `fStartLogging` (tee vers `/root/webapp-install.log`) → nouveau bash → `fRunSteps` : `fParseArguments` → `fCheckRoot` → `fCheckDistro` → (`--reinstall` : `fConfirmReinstall` → `fStopService` → `fRemoveInstallation`) → `fInstallDependencies` → `fCheckPythonVersion` → `fCreateAppUser` → `fCreateDirectories` → `fObtainSourceCode` (copie locale ou archive tar de GitHub) → `fStopService` → `fDeploySourceCode` → `fInstallDefaultConfig` → `fBuildVirtualEnv` → `fInstallSpacyModels` → `fGenerateCertificates` → `fInitializeAdminUser` (`ainonyproxy.py --user-exists` / `--set-user --password-stdin`, puis `fWriteCredentialsFile`) → `fSetPermissions` → `fInstallService` → `fStartService` (systemd/OpenRC, ou un simple processus dans les conteneurs qui n'en ont pas) → `fVerifyInstallation` (interroge `/api/ai/status`) → `fPrintSummary`.

À la sortie, `fCleanup` supprime le code téléchargé et attend que `tee` écrive les dernières lignes.

---

## 5. Points d'entrée et carte des routes

### Web

| Route | Handler | Fichier | Accès |
|---|---|---|---|
| `GET /` | `fRoot` | `backend/routes/dashboard.py` | Redirige vers la connexion ou vers le tableau de bord du rôle |
| `GET /auth/login/` | `fLoginPage` | `backend/routes/auth.py` | Public |
| `GET /auth/register/` | `fRegisterPage` | `backend/routes/auth.py` | Public (inscriptions fermées : affiche un avis) |
| `GET /auth/recover/` | `fRecoverPage` | `backend/routes/auth.py` | Public |
| `GET /admin/dashboard/` | `fAdminDashboardRoot` | `backend/routes/dashboard.py` | admin → 307 vers `overview/` |
| `GET /admin/dashboard/{overview,users,account,help}/` | `fAdminDashboardTab` | `backend/routes/dashboard.py` | admin |
| `GET /user/dashboard/` | `fUserDashboardRoot` | `backend/routes/dashboard.py` | tout utilisateur → 307 vers `api/` |
| `GET /user/dashboard/{api,account,help}/` | `fUserDashboardTab` | `backend/routes/dashboard.py` | tout utilisateur |
| `GET /api/doc/` | Swagger UI de FastAPI | `backend/ainonyproxy.py` | Public |
| `GET /api/doc/redoc/` | ReDoc de FastAPI | `backend/ainonyproxy.py` | Public |
| `GET /api/doc/openapi.json` | FastAPI | `backend/ainonyproxy.py` | Public |
| `GET /api/ai/` | `fListProviders` | `backend/routes/chat.py` | Public |
| `POST /api/ai/{provider}` | `fChatCompletions` | `backend/routes/chat.py` | Public |
| `GET /api/ai/status` | `fStatus` | `backend/routes/health.py` | Public |
| `GET /api/ai/info` | `fInfo` | `backend/routes/info.py` | Public |
| `POST /api/auth/login` | `fApiLogin` | `backend/routes/auth.py` | Public |
| `POST /api/auth/register` | `fApiRegister` | `backend/routes/auth.py` | Public, tant que les inscriptions sont ouvertes |
| `POST /api/auth/recover` | `fApiRecover` | `backend/routes/auth.py` | Public |
| `POST /api/auth/logout` | `fApiLogout` | `backend/routes/auth.py` | Public |
| `GET /api/auth/session` | `fApiSession` | `backend/routes/auth.py` | tout utilisateur |
| `GET /api/admin/logs?limit=&offset=` | `fApiLogs` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/stats` | `fApiStats` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/users` | `fApiListUsers` | `backend/routes/users.py` | admin |
| `POST /api/admin/users` | `fApiCreateUser` | `backend/routes/users.py` | admin |
| `GET /api/admin/registration` | `fApiGetRegistration` | `backend/routes/users.py` | admin |
| `PUT /api/admin/registration` | `fApiSetRegistration` | `backend/routes/users.py` | admin |
| `DELETE /api/admin/users/{username}` | `fApiDeleteUser` | `backend/routes/users.py` | admin |
| `PUT /api/admin/users/{username}/password` | `fApiResetPassword` | `backend/routes/users.py` | admin |
| `GET /api/user/account` | `fApiAccount` | `backend/routes/users.py` | tout utilisateur |
| `PUT /api/user/account/password` | `fApiChangePassword` | `backend/routes/users.py` | tout utilisateur |
| `POST /api/user/account/recovery-code` | `fApiNewRecoveryCode` | `backend/routes/users.py` | tout utilisateur |
| `GET /api/languages` | `fApiLanguages` | `backend/routes/dashboard.py` | Public |
| `GET /api/languages/{code}` | `fApiLanguageFile` | `backend/routes/dashboard.py` | Public |
| `http://*:11080/*` | `fRedirectToHttps` | `backend/ainonyproxy.py` | 308 vers HTTPS |

### Ligne de commande

| Commande | Handler | Fichier |
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

## 6. Analyse d'impact

| Si vous modifiez... | Cela affecte... |
|---|---|
| Les chemins de `config.py` (`cHomeDir` et compagnie) | Les installateurs (mêmes chemins codés en dur dans leurs constantes), `deploy/run.sh`, les unités systemd/OpenRC, tous les documents qui mentionnent `/opt/ainonyproxy/` |
| `AppConfig` et ses sous-modèles | `backend/config-defaults/config.json`, `fSaveConfig`, MANUAL (référence de configuration) |
| Le format de `api_urls.json` / `api_keys.json` | `fLoadConfig`, `fEnsureApiKeys`, `fValidateApiKeys`, installateurs (`fInstallDefaultConfig`) |
| Les formats de `services/dates.py` | Chaque date stockée (`request_logs`, `users`, `user_sessions`), les comparaisons de chaînes des statistiques, du nettoyage et de l'expiration des sessions, `fStorageDateToDisplay` dans le tableau de bord, `view_database.py` |
| Les colonnes de `request_logs` | `RequestRecord`, `RequestLogData`, `mRecord`, `fCreateLogData`, les consommateurs de `fApiLogs` dans `dashboard.html`, `view_database.py` |
| Les tables `users` / `user_sessions` | `UserStore` (son `_mInitializeDatabase` ajoute les colonnes manquantes aux anciennes bases), `view_database.py` (options 1 et 3), installateurs (`--user-exists`, `--set-user`) |
| `MaskingContext` ou le format de marqueur `<TYPE_N>` | `fMask`, `fUnmaskText`, `fUnmaskStreamFragment` (il cherche `<` et `>`), l'expression régulière de mise en évidence des marqueurs dans `dashboard.html` |
| Les champs de `PiiDetectionResult` | `Router`, `fCreateLogData`, les en-têtes de réponse dans `fChatCompletions` |
| Les types de retour de `LlmClient` | `fChatCompletions` (`is_streaming`, `response`, `model`) |
| Le cookie de session (`services/auth.py`) | Chaque page et API protégée, `login.html` et `register.html` (il connecte le nouvel utilisateur), `fApi` dans `dashboard.html` (redirection en cas de 401) |
| `aAdminTabs` / `aUserTabs` | La barre latérale de `dashboard.html`, les clés `tabs.*` de chaque `frontend/lang/*.json`, MANUAL |
| Le format du code de récupération (`cRecoveryCode*`, `fNormalizeRecoveryCode`) | Tous les codes stockés (un nouveau format doit continuer d'accepter les anciens, sinon les utilisateurs devront en générer de nouveaux), le texte indicatif de `recover.html`, MANUAL |
| `app_settings` / `dSettingDefaults` | `SettingsStore`, `/api/admin/registration`, l'onglet Utilisateurs, `register.html` et `login.html` (lien vers l'inscription) |
| Les jetons du thème (`partials/theme-head.html`) | Toutes les pages. Chaque jeton est défini trois fois (sombre, clair selon le système, clair choisi) et les trois blocs doivent avoir les mêmes noms |
| Une clé de `en-US.json` | La même clé dans `en-GB`, `es-AR`, `es-ES`, `fr-FR` |
| Les ports 11080 / 11443 | `config-defaults/config.json`, `fVerifyInstallation` et `fPrintSummary` dans les installateurs, les textes d'aide (`help.endpointCode`), README, MANUAL |
| Les options de CLI de `ainonyproxy.py` | `fInitializeAdminUser` dans les deux installateurs, MANUAL (réinitialisation du mot de passe) |
| `cSourceTarballUrl`, le dépôt ou sa branche `main` | Les deux installateurs (en-tête, `fObtainSourceCode`, la vérification de `sh`), les lignes d'installation de tous les README et MANUAL |

---

## 7. Points d'extension

### Un nouveau fournisseur de LLM

- Compatible OpenAI : ajoutez `"name": {"url": "https://.../v1/chat/completions"}` à `/opt/ainonyproxy/config/api_urls.json` (et à `backend/config-defaults/api_urls.json` pour les nouvelles installations), ajoutez sa clé à `api_keys.json`, puis redémarrez. Il est servi sur `/api/ai/name`.
- Un autre format d'échange : ajoutez la valeur à `cApiFormat` (`config.py`), détectez-la dans `fDetectFormat`, et ajoutez une branche dans `LlmClient.mCompleteChat` qui convertit la requête et la réponse vers la forme OpenAI (voir la branche Anthropic : `_mBuildAnthropicBody`, `_mFormatAnthropicResponse`, `_mCompleteChatStreamingAnthropic`). `gemini` est déclaré mais n'a pas encore de branche : il est envoyé comme compatible OpenAI.

### Un nouvel endpoint d'API

1. Ajoutez la fonction au routeur de son public : `vAdminApiRouter` / `vAdminUsersRouter` (`/api/admin`), `vUserAccountRouter` (`/api/user`), `vChatRouter` (`/api/ai`), ou un nouvel `APIRouter(tags=[...])` inclus dans `ainonyproxy.py` avec un préfixe sous `/api/`.
2. Protégez-la avec `fRequireApiAdmin(pRequest)` ou `fRequireApiUser(pRequest)`.
3. Donnez-lui un `summary` : il apparaît tout seul dans `/api/doc/`.
4. Ajoutez sa ligne à la section 5 de chaque fichier CODE.

### Un nouvel onglet du tableau de bord

1. Ajoutez son nom à `aAdminTabs` ou `aUserTabs` (`routes/dashboard.py`).
2. Ajoutez son icône à `dTabIcons` et son bloc `{% if vTab == "name" %}` à `dashboard.html`, ainsi que son chargeur au bloc de démarrage du script.
3. Ajoutez `tabs.name` (et ses textes) à chaque `frontend/lang/*.json`.
4. Il est aussitôt accessible sur `/admin/dashboard/name/` ou `/user/dashboard/name/`.

### Une nouvelle langue d'interface

Copiez `frontend/lang/en-US.json` vers `frontend/lang/xx-YY.json`, modifiez `meta` et traduisez les valeurs. Elle apparaît toute seule dans le sélecteur.

### Un nouveau réglage du tableau de bord

Ajoutez sa clé et sa valeur par défaut à `dSettingDefaults` (`services/settings.py`) avec une paire de méthodes comme `mIsRegistrationOpen` / `mSetRegistrationOpen`, un endpoint d'administration comme `fApiSetRegistration` sous `/api/admin/`, et son contrôle dans l'onglet auquel il appartient (avec ses textes dans chaque `frontend/lang/*.json`).

### Une nouvelle couleur

Ajoutez la propriété personnalisée aux trois blocs de `partials/theme-head.html` (sombre, clair selon le système, clair choisi) et utilisez-la avec `var(--nom)`. N'écrivez jamais une couleur directement dans une page.

### Une nouvelle langue de PII

Ajoutez son code à `languages` dans `/opt/ainonyproxy/config/pii_detection.json` (il doit figurer dans `cSupportedLanguages`), puis exécutez `presidio/setup.py --languages xx` avec le Python du venv (ou lancez l'installateur avec `--update`) et redémarrez.
