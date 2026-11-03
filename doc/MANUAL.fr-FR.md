# ainonyproxy - MANUAL

Ce MANUAL est également disponible en :\
[en-GB](MANUAL.en-GB.md), [en-US](MANUAL.md), [es-AR](MANUAL.es-AR.md), [es-ES](MANUAL.es-ES.md), fr-FR

Comment installer ainonyproxy, le configurer et l'utiliser au quotidien.

## Sommaire

1. [Ce qu'il fait](#ce-quil-fait)
2. [Sur quoi il fonctionne](#sur-quoi-il-fonctionne)
3. [Installation](#installation)
4. [Mise à jour et réinstallation](#mise-à-jour-et-réinstallation)
5. [Ouvrir l'application](#ouvrir-lapplication)
6. [Se connecter](#se-connecter)
7. [Le tableau de bord administrateur](#le-tableau-de-bord-administrateur)
8. [Le tableau de bord utilisateur](#le-tableau-de-bord-utilisateur)
9. [Thème clair et thème sombre](#thème-clair-et-thème-sombre)
10. [Envoyer des requêtes via ainonyproxy](#envoyer-des-requêtes-via-ainonyproxy)
11. [Fournisseurs et clés d'API](#fournisseurs-et-clés-dapi)
12. [Détection des PII](#détection-des-pii)
13. [Ce qui est écrit dans la base de données](#ce-qui-est-écrit-dans-la-base-de-données)
14. [Référence de configuration](#référence-de-configuration)
15. [Fichiers et dossiers](#fichiers-et-dossiers)
16. [Certificats](#certificats)
17. [Exécution sans le service](#exécution-sans-le-service)
18. [Consulter la base de données](#consulter-la-base-de-données)
19. [Dépannage](#dépannage)
20. [Désinstallation](#désinstallation)

---

## Ce qu'il fait

ainonyproxy est un proxy de confidentialité pour les modèles de langage (LLM). Vos applications envoient leurs requêtes de chat à ainonyproxy au lieu de les envoyer à OpenAI, Anthropic, DeepSeek, un Ollama local, etc. Pour chaque requête, ainonyproxy :

1. Détecte les informations personnelles (noms, adresses e-mail, numéros de téléphone, IBAN, adresses IP, lieux, numéros d'identité...) avec [Presidio](https://microsoft.github.io/presidio/) et spaCy, qui s'exécutent sur votre propre ordinateur.
2. Remplace chaque information personnelle par un marqueur tel que `<PERSON_1>` ou `<EMAIL_ADDRESS_1>`.
3. Envoie la conversation masquée au fournisseur que vous avez choisi.
4. Remet les valeurs réelles dans la réponse avant de la renvoyer à votre application.

Le fournisseur ne voit jamais les données personnelles, et votre application ne remarque rien : elle parle l'API de chat d'OpenAI, avec ou sans streaming.

Il dispose aussi d'un tableau de bord web, avec un thème clair et un thème sombre, qui affiche des statistiques et les dernières requêtes et gère les utilisateurs (qui peuvent créer leur propre compte et récupérer leur mot de passe eux-mêmes).

## Sur quoi il fonctionne

| | |
|---|---|
| Système d'exploitation | Debian 13 (trixie) ou ultérieur, ou Alpine Linux avec un paquet `python3` en version 3.13 ou ultérieure |
| Python | 3.13 ou ultérieur (l'installateur le vérifie) |
| Disque | Environ 3 Go (paquets Python et modèles de langue spaCy) |
| Mémoire | 2 Go ou plus (chaque modèle de langue spaCy est chargé en mémoire) |
| Réseau | Accès aux fournisseurs de LLM que vous utilisez, ainsi qu'à PyPI et GitHub pendant l'installation |
| Ports | `11080` (HTTP, il ne fait que rediriger) et `11443` (HTTPS) |

Il est conçu pour être utilisé depuis le même ordinateur que celui sur lequel il s'exécute : vos applications s'adressent à `https://localhost:11443`.

## Installation

Exécutez l'installateur en tant que `root`. Il fait tout seul et ne pose aucune question.

**Debian** (une Debian minimale, comme l'image Docker, n'a pas curl, la ligne l'installe donc d'abord) :

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --install
```

**Alpine Linux** (il n'a pas bash par défaut, la ligne l'installe donc d'abord) :

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install
```

Vous pouvez aussi l'exécuter depuis une copie du dépôt : `bash deploy/install-update-reinstall-debian.sh --install`. Dans ce cas, il utilise le code de cette copie au lieu de le télécharger.

Vous pouvez le relancer sans crainte : les installateurs sont idempotents, donc en exécuter un deux fois avec la même option laisse le système dans le même état qu'une seule exécution. Ils sont conçus pour être téléchargés avec `curl` et envoyés directement à `bash` : rien ne s'exécute avant l'arrivée du script complet, donc un téléchargement interrompu à mi-chemin ne fait rien. Envoyez-les à `bash`, pas à `sh` : avec `sh`, ils s'arrêtent et vous le signalent.

### Ce que fait l'installateur

1. Installe les paquets système dont il a besoin (Python, compilateur, OpenSSL, curl...).
2. Vérifie que Python est en version 3.13 ou ultérieure.
3. Crée l'utilisateur système `ainonyproxy` (sans mot de passe, sans shell de connexion), dont le répertoire personnel est `/opt/ainonyproxy/`.
4. Copie le code dans `/opt/ainonyproxy/webapp/` et crée l'environnement virtuel Python dans `/opt/ainonyproxy/venv/`.
5. Copie la configuration par défaut dans `/opt/ainonyproxy/config/` (uniquement les fichiers qui n'existent pas encore : il n'écrase jamais les vôtres).
6. Installe les modèles spaCy des langues configurées dans `pii_detection.json`.
7. Crée un certificat autosigné lorsqu'il n'y a pas de certificat Let's Encrypt.
8. Crée l'administrateur du tableau de bord `admin` avec un mot de passe aléatoire (uniquement la première fois).
9. Installe et démarre le service (`systemd` sur Debian, `OpenRC` sur Alpine) et attend qu'il réponde.

La première installation prend plusieurs minutes : les paquets Python et les modèles spaCy sont volumineux. Sur Alpine, certains paquets peuvent devoir être compilés, ce qui prend plus de temps.

### Où se trouve le mot de passe

| Fichier | Contenu |
|---|---|
| `/root/webapp-credentials.txt` | L'utilisateur et le mot de passe de l'administrateur du tableau de bord |
| `/root/webapp-install.log` | Tout ce que l'installateur a fait, avec la sortie de chaque commande |

Les deux ne sont lisibles que par root (mode `600`).

### Dans les conteneurs

Dans un conteneur sans systemd (Docker), l'installateur démarre ainonyproxy comme un simple processus en arrière-plan et vous avertit qu'il ne redémarrera pas tout seul après un redémarrage du conteneur : relancez l'installateur pour le démarrer. Sur Alpine, il prépare OpenRC afin que le service puisse s'exécuter dans le conteneur.

## Mise à jour et réinstallation

| Commande | Ce qu'elle fait |
|---|---|
| `--install` | Installe. Sur une installation existante, elle se comporte comme `--update`. |
| `--update` | Remplace le code et met à jour les dépendances et les modèles. Conserve la configuration, la base de données, les utilisateurs, les certificats et les mots de passe. |
| `--reinstall` | Supprime le code, l'environnement virtuel, la configuration, la base de données et les journaux (**pas** les certificats) et réinstalle de zéro, avec un nouveau mot de passe administrateur. Elle demande une confirmation ; ajoutez `--yes` pour ignorer la question. |

```bash
curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --update
```

## Ouvrir l'application

| Quoi | Adresse |
|---|---|
| Tableau de bord | `https://localhost:11443/` (il vous mène à la connexion) |
| Connexion | `https://localhost:11443/auth/login/` |
| Créer un compte | `https://localhost:11443/auth/register/` (quand les inscriptions sont ouvertes) |
| Récupérer le mot de passe | `https://localhost:11443/auth/recover/` |
| API d'IA | `https://localhost:11443/api/ai/{provider}` |
| Documentation de l'API (Swagger) | `https://localhost:11443/api/doc/` |
| Statut | `https://localhost:11443/api/ai/status` |

Tout ce qui arrive sur `http://...:11080` est redirigé de façon permanente vers la même adresse en `https://...:11443`.

Avec le certificat autosigné, le navigateur affiche un avertissement la première fois : c'est normal, la connexion est chiffrée malgré tout. Consultez [Certificats](#certificats) pour en utiliser un vrai.

## Se connecter

Ouvrez le tableau de bord et connectez-vous avec l'utilisateur et le mot de passe de `/root/webapp-credentials.txt`. Si vous ouvrez l'adresse d'un tableau de bord sans être connecté, vous êtes envoyé vers la connexion puis, une fois connecté, ramené à la page demandée.

Il existe deux rôles :

| Rôle | Ce qu'il peut faire |
|---|---|
| `admin` | Tout : les deux tableaux de bord, les statistiques, les journaux de requêtes, la gestion des utilisateurs |
| `user` | Le tableau de bord utilisateur : données de connexion à l'API, mot de passe personnel |

Une session dure 12 heures (`dashboard.session_hours`). Après 5 tentatives échouées depuis la même adresse, la connexion se bloque pendant 15 minutes.

### Créer un compte

Quand les inscriptions sont ouvertes, toute personne qui arrive sur la page de connexion peut créer un compte sur `/auth/register/` (lien « Créer un compte » de la page de connexion). Ces comptes ont toujours le rôle `user` : seul un administrateur peut rendre quelqu'un `admin`. Les inscriptions sont ouvertes par défaut, et un administrateur les ouvre ou les ferme dans **Utilisateurs → Inscriptions**. Une même adresse peut créer jusqu'à 5 comptes par heure.

Juste après la création du compte, la page affiche une seule fois son code de récupération. Quand vous confirmez l'avoir conservé, « Aller à mon tableau de bord » ouvre le tableau de bord utilisateur, déjà connecté.

### Codes de récupération

Chaque compte peut avoir un code de récupération, comme `ABCDE-FGHJK-LMNPQ-RSTUV`, pour définir un nouveau mot de passe sans administrateur. Il n'est affiché qu'une seule fois : ainonyproxy ne garde que son empreinte (SHA-256), personne ne peut donc l'afficher de nouveau. Copiez-le ou notez-le, et conservez-le en lieu sûr.

| Quand | Qui voit le code |
|---|---|
| Vous créez votre compte sur `/auth/register/` | Vous |
| Un administrateur crée votre utilisateur dans **Utilisateurs** | L'administrateur, qui vous le remet |
| Vous appuyez sur **Générer un nouveau code de récupération** dans **Compte** (il demande votre mot de passe actuel) | Vous. Le code précédent cesse de fonctionner. |
| Vous l'utilisez sur `/auth/recover/` | Vous en recevez un nouveau : chaque code ne sert qu'une fois |

L'administrateur créé par l'installateur et les utilisateurs créés depuis le terminal commencent sans code : générez-en un dans **Compte**.

### Mot de passe oublié

Ouvrez `/auth/recover/` (lien « Mot de passe oublié ? » de la page de connexion) et saisissez votre nom d'utilisateur, votre code de récupération (avec ou sans tirets, en majuscules ou en minuscules) et deux fois le nouveau mot de passe. Le mot de passe change, toutes les sessions du compte sont fermées et la page affiche votre nouveau code de récupération. Les tentatives erronées comptent comme des connexions échouées : après 5 depuis la même adresse, il faut attendre 15 minutes.

Sans code de récupération, un administrateur peut vous attribuer un nouveau mot de passe dans **Utilisateurs**, et root peut le faire depuis le terminal du serveur (section suivante).

### Réinitialiser un mot de passe depuis le terminal

Si plus personne ne peut se connecter, définissez un nouveau mot de passe depuis le serveur, en tant que root :

```bash
printf '%s\n' 'TheNewPassword' | AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/ainonyproxy.py --set-user admin --role admin --password-stdin
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/db
```

La même commande crée l'utilisateur s'il n'existe pas. `--list-users` liste les utilisateurs. Les mots de passe doivent comporter au moins 8 caractères.

## Le tableau de bord administrateur

`/admin/dashboard/` ouvre l'onglet **Aperçu**. Chaque onglet a sa propre adresse : vous pouvez donc l'ajouter à vos favoris ou l'ouvrir directement.

| Onglet | Adresse | Contenu |
|---|---|---|
| Aperçu | `/admin/dashboard/overview/` | Total des requêtes, requêtes avec des PII masquées, durée moyenne d'analyse, requêtes de la dernière heure, les types d'entités PII les plus détectés et les 50 dernières requêtes. S'actualise toutes les 5 secondes. Cliquez sur une requête pour voir son contenu masqué (lorsqu'il est enregistré). |
| Utilisateurs | `/admin/dashboard/users/` | Ouvrir ou fermer les inscriptions sur `/auth/register/`. Créer des utilisateurs (nom, mot de passe, rôle) : le code de récupération du nouvel utilisateur est affiché une fois, pour que vous le lui remettiez. Leur attribuer un nouveau mot de passe, les supprimer. Le dernier administrateur et votre propre utilisateur ne peuvent pas être supprimés. |
| Compte | `/admin/dashboard/account/` | Vos données, le formulaire pour changer votre mot de passe (le changer ferme vos autres sessions) et celui pour générer un nouveau code de récupération. |
| Aide | `/admin/dashboard/help/` | Un résumé de l'utilisation d'ainonyproxy. |

La barre latérale comporte aussi un lien vers le tableau de bord utilisateur, le bouton de déconnexion, le sélecteur de thème (voir [Thème clair et thème sombre](#thème-clair-et-thème-sombre)) et le sélecteur de langue (en-GB, en-US, es-AR, es-ES, fr-FR). Toutes les heures sont affichées en UTC avec le format `2026/10/29@13:59:59.723`.

## Le tableau de bord utilisateur

`/user/dashboard/` ouvre l'onglet **API**.

| Onglet | Adresse | Contenu |
|---|---|---|
| API | `/user/dashboard/api/` | L'URL de base, un exemple avec `curl` et le tableau des fournisseurs disponibles avec leur endpoint. |
| Compte | `/user/dashboard/account/` | Vos données, le formulaire pour changer votre mot de passe et celui pour générer un nouveau code de récupération. |
| Aide | `/user/dashboard/help/` | Un résumé de l'utilisation d'ainonyproxy. |

## Thème clair et thème sombre

Toutes les pages (connexion, inscription, récupération du mot de passe et les deux tableaux de bord) ont un thème clair et un thème sombre. Le sélecteur de thème se trouve en bas de la barre latérale des tableaux de bord, et sous la carte des pages de connexion. Il comporte trois boutons :

| Bouton | Thème |
|---|---|
| Système (icône d'écran) | Le thème de votre système d'exploitation. C'est le choix par défaut, et la page change d'elle-même quand celui du système change. |
| Clair (icône de soleil) | Toujours clair. |
| Sombre (icône de lune) | Toujours sombre. |

Le choix est mémorisé dans ce navigateur (`localStorage`, clé `ainonyproxy_theme`) et s'applique à toutes les pages d'ainonyproxy qui y sont ouvertes.

## Envoyer des requêtes via ainonyproxy

Faites pointer votre application vers `https://localhost:11443/api/ai/{provider}` au lieu de l'URL du fournisseur, et envoyez la même requête de chat au style OpenAI :

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

Le fournisseur reçoit `Write an e-mail to <PERSON_1>, his address is <EMAIL_ADDRESS_1>` et votre application reçoit la réponse avec le vrai nom et la vraie adresse remis en place.

- `-k` indique à curl d'accepter le certificat autosigné. D'autres clients ont une option similaire, ou vous pouvez installer le certificat comme certificat de confiance.
- Ajoutez `"stream": true` pour le streaming (Server-Sent Events, comme OpenAI).
- `messages` accepte les rôles `system`, `user` et `assistant`, avec un contenu textuel.
- Les autres champs (`temperature`, `max_tokens`, `stop`...) sont transmis au fournisseur. Pour Anthropic, ils sont convertis dans son format.
- `GET /api/ai/` liste les fournisseurs avec leur URL complète.

### En-têtes de réponse

| En-tête | Signification |
|---|---|
| `X-Ainonyproxy-Provider` | Fournisseur utilisé |
| `X-Ainonyproxy-PII-Detected` | `true` lorsque le dernier message de l'utilisateur contenait des PII |
| `X-Ainonyproxy-PII-Masked` | `true` lorsque la conversation a été masquée |
| `X-Ainonyproxy-Language` | Langue utilisée pour la détection |
| `X-Ainonyproxy-Language-Fallback` | `true` lorsque la langue détectée n'était pas configurée et que la langue de repli a été utilisée |
| `X-Request-ID` | Identifiant de la requête (le vôtre, si vous en avez envoyé un) |

### Erreurs

| Code | Quand |
|---|---|
| `400` | Le corps n'est pas une requête de chat valide |
| `404` | Le fournisseur n'existe pas |
| `502` | Le fournisseur a répondu par une erreur, ou n'a pas pu être joint |
| `503` | La détection des PII n'est pas disponible |

## Fournisseurs et clés d'API

Les fournisseurs se trouvent dans `/opt/ainonyproxy/config/api_urls.json` :

```json
{
  "openai": { "url": "https://api.openai.com/v1/chat/completions" },
  "anthropic": { "url": "https://api.anthropic.com/v1/messages" },
  "ollama": { "url": "http://localhost:11434/v1/chat/completions" }
}
```

Chaque entrée peut aussi comporter `"format"` (`openai` ou `anthropic` ; il est déduit de l'URL s'il est absent) et `"model"` (un modèle toujours utilisé, quel que soit celui que demande le client). Le nom de l'entrée est le nom utilisé dans l'URL : `/api/ai/openai`.

Les clés se trouvent dans `/opt/ainonyproxy/config/api_keys.json`, à part du reste afin que ce fichier seul contienne les secrets :

```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-...",
  "ollama": ""
}
```

Les fournisseurs locaux (`localhost`, `10.x`, `172.16-31.x`, `192.168.x`) peuvent avoir une clé vide. Les valeurs peuvent utiliser des variables d'environnement : `"${OPENAI_API_KEY}"`.

Après avoir modifié l'un ou l'autre de ces fichiers, conservez le propriétaire et redémarrez :

```bash
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/config/*.json
chmod 600 /opt/ainonyproxy/config/*.json
systemctl restart ainonyproxy        # Debian
rc-service ainonyproxy restart       # Alpine
```

Inclus par défaut : `anthropic`, `deepseek`, `gemini`, `kimi`, `llamacpp`, `ollama`, `openai`, `openrouter`, `vllm` et `zai`. `gemini` est déclaré mais est envoyé comme compatible OpenAI, ce que l'API Gemini native ne comprend pas ; et `llamacpp` pointe vers `/completion`, qui n'est pas un endpoint de chat. Utilisez l'URL compatible OpenAI de ces serveurs si vous en avez besoin.

## Détection des PII

Elle se configure dans `/opt/ainonyproxy/config/pii_detection.json` :

| Clé | Signification | Par défaut |
|---|---|---|
| `languages` | Langues à détecter (codes spaCy : `en`, `es`, `fr`, `de`, `it`, `pt`, `ca`...) | `["es", "en"]` |
| `fallback_language` | Langue utilisée lorsque la langue détectée ne figure pas dans la liste | `es` |
| `score_threshold` | Confiance minimale (de 0 à 1) pour considérer un élément comme une PII. Plus elle est basse, plus on en trouve, mais aussi plus de faux positifs. | `0.5` |
| `entities` | Types d'entités Presidio à rechercher | Une longue liste (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN_CODE`, `ES_NIF`...) |

Chaque langue a besoin de son modèle spaCy. Après en avoir ajouté une, installez son modèle et redémarrez :

```bash
/opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/presidio/setup.py --languages fr
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/venv
systemctl restart ainonyproxy
```

Vous pouvez aussi lancer l'installateur avec `--update`, qui installe les modèles de chaque langue configurée. ainonyproxy refuse de démarrer lorsqu'une langue configurée n'a pas de modèle, afin de ne jamais laisser passer des données personnelles par erreur.

Seul le dernier message de l'utilisateur détermine si une conversation contient des PII. Lorsque c'est le cas, chaque message de l'utilisateur et de l'assistant est masqué, et la même valeur reçoit toujours le même marqueur.

## Ce qui est écrit dans la base de données

Chaque requête est enregistrée dans `/opt/ainonyproxy/db/ainonyproxy.db` : heure, fournisseur, modèle, présence ou non de PII, types d'entités, langue, durées et tokens. L'enregistrement ou non des textes dépend de `config.json` :

| Clé | Ce qu'elle contrôle | Par défaut |
|---|---|---|
| `logging.log_content` | Requête d'origine et réponse au client (avec les vraies données personnelles) | `false` |
| `logging.log_masked_content` | Requête masquée et réponse du fournisseur (avec des marqueurs) | `true` |
| `logging.retention_days` | Nombre de jours de conservation d'une requête ; `0` les conserve indéfiniment | `30` |

Avec les valeurs par défaut, la base de données ne contient jamais les données personnelles elles-mêmes.

La même base de données contient les utilisateurs du tableau de bord (seulement les empreintes de leurs mots de passe et de leurs codes de récupération, jamais les valeurs), leurs sessions (seulement l'empreinte de chaque jeton) et les réglages qu'un administrateur modifie depuis le tableau de bord (table `app_settings`, par exemple si les inscriptions sont ouvertes).

## Référence de configuration

`/opt/ainonyproxy/config/config.json` :

| Clé | Signification | Par défaut |
|---|---|---|
| `mode` | Seul `mask` existe | `mask` |
| `server.host` | Adresse d'écoute | `0.0.0.0` |
| `server.port` | Port HTTP (il ne fait que rediriger vers HTTPS) | `11080` |
| `server.ssl_port` | Port HTTPS | `11443` |
| `server.proxy_protocol` | Attendre le protocole PROXY sur HTTPS (pour un HAProxy placé devant avec `send-proxy`) | `false` |
| `server.ssl.enabled` / `certfile` / `keyfile` | Certificat personnel, utilisé lorsqu'il n'y a pas de certificat Let's Encrypt dans le dossier des certificats | `false` |
| `masking.show_markers` | Placer `marker_text` devant chaque valeur démasquée dans les réponses | `false` |
| `masking.marker_text` | Texte utilisé par `show_markers` | `[protected]` |
| `logging.*` | Voir [Ce qui est écrit dans la base de données](#ce-qui-est-écrit-dans-la-base-de-données) | |
| `logging.database` | Chemin de la base de données SQLite | `/opt/ainonyproxy/db/ainonyproxy.db` |
| `dashboard.enabled` | Réservé ; le tableau de bord est toujours disponible | `true` |
| `dashboard.session_hours` | Durée d'une session du tableau de bord | `12` |
| `ui.default_language` | Langue de l'interface pour qui n'en a pas choisi | `en-US` |

Redémarrez le service après toute modification.

## Fichiers et dossiers

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

Tout appartient à l'utilisateur `ainonyproxy`. `config/`, `db/` et `certificates/` ne sont lisibles que par lui (et par root).

## Certificats

Sans rien d'autre, ainonyproxy sert le HTTPS avec un certificat autosigné (`/opt/ainonyproxy/certificates/selfsigned-fullchain.pem`), valable pour `localhost`, `127.0.0.1` et le nom de la machine.

Pour utiliser un certificat Let's Encrypt, copiez ses deux fichiers dans le dossier des certificats avec ces noms, puis redémarrez :

```bash
cp /etc/letsencrypt/live/your.domain/fullchain.pem /opt/ainonyproxy/certificates/fullchain.pem
cp /etc/letsencrypt/live/your.domain/privkey.pem /opt/ainonyproxy/certificates/privkey.pem
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/certificates/*.pem
chmod 600 /opt/ainonyproxy/certificates/privkey.pem
systemctl restart ainonyproxy
```

Ils ont priorité sur tout le reste. Répétez la copie après chaque renouvellement.

## Exécution sans le service

`deploy/run.sh` (dans une copie du dépôt) crée l'environnement virtuel, installe ce qui manque et démarre ainonyproxy au premier plan, en affichant tout ce qu'il fait. Arrêtez-le avec `Ctrl+C`.

```bash
bash deploy/run.sh                                   # as root, uses /opt/ainonyproxy
AINONYPROXY_HOME="$PWD/_/temp/home" bash deploy/run.sh   # as any user, in a folder of your own
```

Si le service installé est en cours d'exécution, arrêtez-le d'abord : les deux utilisent les mêmes ports (ainonyproxy arrête tout ce qui y écoute encore avant de démarrer).

Lorsqu'il n'y a pas encore d'utilisateurs (il n'a jamais été installé), le premier démarrage crée `admin` et affiche son mot de passe une seule fois dans le terminal.

## Consulter la base de données

```bash
AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/view_database.py
```

Un menu affiche les utilisateurs, les sessions, les dernières requêtes, le détail d'une requête, les contenus masqués et des statistiques générales.

## Dépannage

| Ce qui se passe | Que faire |
|---|---|
| Le service ne démarre pas | `journalctl -u ainonyproxy -n 100 --no-pager` (Debian) ou `/opt/ainonyproxy/logs/ainonyproxy.log` (Alpine et conteneurs). |
| `Missing spaCy models` (message du journal, en anglais) | Installez les modèles des langues configurées (voir [Détection des PII](#détection-des-pii)) ou lancez l'installateur avec `--update`. |
| Un fournisseur répond 502 | Vérifiez son URL dans `api_urls.json` et sa clé dans `api_keys.json`. Le détail de l'erreur figure dans la réponse. |
| `Remote providers without an API key` au démarrage (message du journal, en anglais) | Ajoutez leurs clés à `api_keys.json`, ou ignorez-le pour les fournisseurs que vous n'utilisez pas. |
| Le navigateur avertit au sujet du certificat | Normal avec le certificat autosigné. Voir [Certificats](#certificats). |
| « Trop de tentatives échouées » | Attendez 15 minutes, ou redémarrez le service. |
| Personne ne se souvient du mot de passe admin | Voir [Réinitialiser un mot de passe depuis le terminal](#réinitialiser-un-mot-de-passe-depuis-le-terminal). |
| « Les inscriptions sont fermées » | Un administrateur les ouvre dans **Utilisateurs → Inscriptions**, ou vous crée le compte. |
| Code de récupération perdu | Tant que vous pouvez vous connecter, générez-en un nouveau dans **Compte → Code de récupération**. Si vous ne pouvez pas vous connecter, un administrateur vous attribue un nouveau mot de passe dans **Utilisateurs**. |
| Le premier démarrage est long | Le chargement des modèles spaCy prend de quelques secondes à une minute ; l'installateur attend jusqu'à 3 minutes. |

## Désinstallation

En tant que root :

```bash
systemctl disable --now ainonyproxy && rm -f /etc/systemd/system/ainonyproxy.service && systemctl daemon-reload   # Debian
rc-service ainonyproxy stop; rc-update del ainonyproxy default; rm -f /etc/init.d/ainonyproxy                     # Alpine
rm -rf /opt/ainonyproxy
userdel ainonyproxy     # Debian (on Alpine: deluser ainonyproxy)
rm -f /root/webapp-credentials.txt /root/webapp-install.log
```
