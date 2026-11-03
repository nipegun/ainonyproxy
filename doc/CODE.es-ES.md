# ainonyproxy - CODE

Este CODE también está disponible en:\
[en-GB](CODE.en-GB.md), [en-US](CODE.md), [es-AR](CODE.es-AR.md), es-ES, [fr-FR](CODE.fr-FR.md)

Referencia técnica de ainonyproxy, para desarrolladores y para modelos de IA. Está pensada para consultarse de forma quirúrgica: salta a la sección que necesites, no la leas de principio a fin.

## Índice

1. [Arquitectura y decisiones de diseño](#1-arquitectura-y-decisiones-de-diseño)
2. [Mapa de módulos](#2-mapa-de-módulos)
3. [Índice de símbolos clave](#3-índice-de-símbolos-clave)
4. [Flujos principales](#4-flujos-principales)
5. [Punto de entrada y mapa de rutas](#5-punto-de-entrada-y-mapa-de-rutas)
6. [Análisis de impacto](#6-análisis-de-impacto)
7. [Puntos de extensión](#7-puntos-de-extensión)

---

## 1. Arquitectura y decisiones de diseño

### Qué es

ainonyproxy es una aplicación FastAPI que se sitúa entre un cliente de chat y un proveedor de LLM. Para cada petición detecta los datos personales (PII) con un Presidio integrado, los sustituye por marcadores como `<PERSON_1>`, envía la conversación enmascarada al proveedor y vuelve a poner los valores reales en la respuesta antes de devolverla. Las peticiones, las estadísticas y los usuarios del panel viven en una única base de datos SQLite.

### Un proceso, dos puertos de escucha

El proceso escucha siempre en dos puertos:

| Puerto | Quién responde | Por qué |
|---|---|---|
| `11080` (HTTP) | Una pequeña aplicación FastAPI construida por `fCreateRedirectApp` | Sólo responde con un `308 Permanent Redirect` a la misma ruta en HTTPS. Se usa 308 (y no 301) porque conserva el método y el cuerpo, de modo que un cliente que hace un POST a HTTP por error no se convierte en un GET. |
| `11443` (HTTPS) | La aplicación real, `vApp` | Todo lo demás: API, paneles, documentación. |

HTTPS nunca es opcional. El certificado se elige en este orden: los archivos de Let's Encrypt de `/opt/ainonyproxy/certificates/` (`fullchain.pem` + `privkey.pem`), después los archivos indicados en `config.json` (`server.ssl`) y, por último, un certificado autofirmado (`selfsigned-fullchain.pem` + `selfsigned-privkey.pem`) que crea el instalador, o la propia aplicación con `openssl`, cuando falta.

Con `server.proxy_protocol: true` los dos puertos se sirven con Hypercorn, que entiende el protocolo PROXY que HAProxy envía con `send-proxy`. En caso contrario se sirven con Uvicorn dentro del mismo bucle de eventos.

El software está pensado para usarse desde el mismo ordenador en el que se ejecuta, así que no hay ninguna configuración de proxy que elegir.

### Todo lo que guarda la aplicación vive en `/opt/ainonyproxy/`

| Ruta | Contenido | Permisos |
|---|---|---|
| `/opt/ainonyproxy/webapp/` | Código: `backend/` y `frontend/` copiados del repositorio | propietario `ainonyproxy` |
| `/opt/ainonyproxy/venv/` | Entorno virtual de Python | propietario `ainonyproxy` |
| `/opt/ainonyproxy/config/` | `config.json`, `api_urls.json`, `api_keys.json`, `api_models.json`, `pii_detection.json` | `700`, archivos `600` |
| `/opt/ainonyproxy/db/ainonyproxy.db` | SQLite: `request_logs`, `users`, `user_sessions`, `app_settings` | `700`, archivo `600` |
| `/opt/ainonyproxy/certificates/` | Certificado de Let's Encrypt o autofirmado | `700`, claves `600` |
| `/opt/ainonyproxy/logs/` | Salida del proceso cuando no se ejecuta bajo systemd | `750` |
| `/opt/ainonyproxy/run/` | Archivo PID cuando se ejecuta sin gestor de servicios | `750` |

`config.py` construye todas las rutas a partir de `cHomeDir`, que es `/opt/ainonyproxy` salvo que la variable de entorno `AINONYPROXY_HOME` diga otra cosa (sólo se usa para ejecutar el código desde un checkout). La configuración del repositorio (`backend/config-defaults/`) es sólo una plantilla: el instalador copia cada archivo a `/opt/ainonyproxy/config/` cuando todavía no existe, de modo que una actualización nunca sobrescribe lo que ha cambiado el usuario.

El proceso se ejecuta como el usuario de sistema `ainonyproxy` (sin contraseña y sin shell de inicio de sesión), el único aparte de root que puede leer la configuración, la base de datos y las claves.

### Configuración repartida en varios archivos

`fLoadConfig` lee `config.json` y después sobrescribe dos secciones con sus propios archivos: `providers` se construye a partir de `api_urls.json` (URL, formato, modelo por defecto) más `api_keys.json` (claves), y `pii_detection` viene de `pii_detection.json`. Las claves viven aparte para que el archivo con los secretos pueda ser `600` y nunca se muestre ni se copie junto con el resto. Cualquier cadena puede usar `${VAR}` o `${VAR:-default}`, que se sustituyen a partir del entorno.

Cuando faltan claves, `fEnsureApiKeys` las pide sólo si hay una terminal. Bajo systemd u OpenRC no la hay, así que escribe entradas vacías y continúa: un servicio nunca debe quedarse esperando una entrada.

### Detección de PII: sólo decide el último mensaje del usuario

`PiiDetector.mAnalyzeMessages` analiza únicamente el último mensaje `user` con contenido. Si no tiene PII, la conversación sale tal cual. Si tiene PII, `mAnalyzeAllMessages` analiza todos los mensajes `user` y `assistant` (con el idioma detectado en el último) y `fMaskMessages` los enmascara todos con un único `MaskingContext` compartido, de modo que el mismo valor recibe el mismo marcador en toda la conversación. Así el coste del caso habitual (sin PII) se queda en un único análisis.

La detección de idioma (`langdetect`) sólo sirve para elegir qué pipeline de Presidio usar. Si el idioma detectado no está configurado, se usa el idioma de respaldo y la petición se marca (`X-Ainonyproxy-Language-Fallback`).

Al arrancar, la aplicación se niega a ejecutarse si un idioma configurado no tiene instalado su modelo de spaCy: detectar PII con el modelo equivocado dejaría pasar datos en silencio.

### Desenmascarado

`fUnmaskText` sustituye los marcadores del más largo al más corto, de modo que `<PERSON_10>` nunca queda roto por `<PERSON_1>`. En streaming, `fUnmaskStreamFragment` guarda en un búfer todo lo que hay después de un `<` que todavía no tiene su `>`, porque un marcador puede llegar partido en dos fragmentos; `fFlushStreamBuffer` lo vacía al final.

### Lo que se escribe en la base de datos

`fCreateLogData` obedece dos interruptores de `config.json` (`logging`):

| Interruptor | Columnas que controla | Por defecto |
|---|---|---|
| `log_content` | `original_content`, `client_response` (textos reales, sin enmascarar) | `false` |
| `log_masked_content` | `masked_content`, `provider_response` (textos enmascarados) | `true` |

Por tanto, por defecto la base de datos nunca contiene los datos personales en sí. `fPeriodicCleanupTask` elimina las peticiones anteriores a `retention_days` una vez al arrancar y después cada 24 horas.

### Fechas

El formato nativo es el formato de almacenamiento de las reglas: UTC, `2026-10-29@13-59-59.723`. Es el que produce `services/dates.py` (`fNowStorage`) y el que produce el propio SQLite como valor por defecto de una columna (`cSqliteStorageNow`). Este formato se ordena como texto, así que "la última hora" y "anterior a 30 días" son simples comparaciones de cadenas. La interfaz muestra `2026/10/29@13:59:59.723` (`fStorageToDisplay` en Python, `fStorageDateToDisplay` en JavaScript). Cualquier otro formato debe derivarse del nativo mediante una función, nunca escribirse a mano.

### Usuarios y sesiones del panel

Hay dos roles: `admin` y `user`. Las contraseñas se guardan como PBKDF2-SHA256 (600 000 iteraciones, sal aleatoria). Un inicio de sesión crea un token aleatorio: el navegador lo conserva en la cookie `ainonyproxy_session` (`Secure`, `HttpOnly`, `SameSite=Strict`) y la base de datos guarda sólo su SHA-256 (`user_sessions.token_hash`), de modo que una copia de la base de datos no regala sesiones válidas. Cambiar una contraseña cierra las otras sesiones de esa cuenta; cuando un administrador establece la contraseña de otra persona, se cierran todas las sesiones de esa persona. El último administrador no se puede eliminar.

`/api/auth/login` permite 5 intentos fallidos por dirección de cliente cada 15 minutos (en memoria). Un inicio de sesión para un usuario que no existe hace el mismo trabajo de PBKDF2 que uno real, de modo que el tiempo de respuesta no revela qué usuarios existen.

También se pueden crear cuentas en `/auth/register/` mientras el ajuste `registration_open` (tabla `app_settings`, `services/settings.py`) sea verdadero, que es su valor por defecto; siempre reciben el rol `user`. `/api/auth/register` permite 5 cuentas por dirección de cliente cada hora (en memoria).

Cada cuenta puede tener un código de recuperación (`fGenerateRecoveryCode`: 20 caracteres de un alfabeto de 32, 100 bits aleatorios). Igual que con los tokens de sesión, sólo se guarda su SHA-256 (`users.recovery_code_hash`); se compara en tiempo constante y `UserStore.mRecoverPassword` lo gasta: nueva contraseña, todas las sesiones cerradas y un código nuevo devuelto. `/api/auth/recover` cuenta sus fallos en el mismo freno que el inicio de sesión. Un código sólo se muestra una vez: en el registro, al administrador que crea un usuario, cuando el usuario genera uno nuevo en Cuenta (pide la contraseña actual) y tras una recuperación.

Los ajustes que se cambian desde el panel viven en `app_settings` y no en `config.json`, de modo que guardarlos nunca reescribe los archivos que el usuario edita a mano (ni sus referencias `${VAR}`).

El primerísimo arranque sin ningún usuario (sólo posible al ejecutar sin el instalador) crea `admin` con una contraseña aleatoria y la imprime una única vez.

### Decisiones de seguridad

- CORS permite cualquier origen pero **sin credenciales**: una página web de otro sitio puede llamar a la API de IA, pero nunca puede aprovechar la sesión del panel de quien la visita. `SameSite=Strict` ya impide, de todos modos, que la cookie viaje en peticiones entre sitios.
- Todo valor que viene del servidor o de un usuario se escapa con `fEscapeHtml` antes de entrar en `innerHTML` (el nombre del modelo de una petición llegó a ser un XSS).
- El parámetro `next` del inicio de sesión sólo acepta rutas de este mismo sitio (`fIsSafeNextPath`), de modo que el inicio de sesión no se puede usar para redirigir a otro lugar.
- Toda respuesta lleva `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy: same-origin`.
- `fFreePort` detiene lo que siga escuchando en 11080 o en 11443 antes de ponerse a escuchar (una instancia anterior que se haya quedado), como piden las reglas.

### Por qué los instaladores ejecutan sus pasos en un bash nuevo

Las reglas exigen `set -euo pipefail` y terminar con `if ! fMain; then ... fi`. Pero una función invocada como condición de un `if` se ejecuta con `set -e` suspendido, y también todo lo que ella llama, incluso un proceso hijo en segundo plano (medido con bash 5.2). Por eso `fMain` exporta todas las funciones y todas las variables `c*`/`v*` y ejecuta `fRunSteps` en un `bash -c 'set -euo pipefail; ...'` nuevo, que recupera `set -e`: el primer comando que falla detiene la instalación y `if ! fMain` lo notifica. `deploy/run.sh` hace lo mismo.

### Por qué los instaladores se pueden pasar de curl a bash

Los instaladores están pensados para ejecutarse como `curl -fsSL <URL raw> | bash -s -- --install`, directamente desde el repositorio de GitHub, y para ser idempotentes: ejecutar uno dos veces con la misma opción deja el sistema igual que ejecutarlo una sola vez (cada paso comprueba antes de actuar: usuario existente, archivos de configuración existentes, certificado existente, administrador existente). Lo que hace segura la tubería:

- Bash ejecuta un script que llega por una tubería mientras todavía está llegando. El nivel superior solo define constantes y funciones, y la última línea (`if ! fMain "$@"; then ... fi`) las ejecuta, así que una descarga cortada a medias no ejecuta nada.
- La entrada estándar del bash de la tubería es el propio script. `fRunSteps` se ejecuta con la entrada estándar en `/dev/null`, así que ningún comando (apt, pip, python) puede tragarse el resto del script. La única pregunta, `--reinstall` sin `--yes`, lee de `/dev/tty`, y sin terminal se detiene y pide `--yes`.
- `vScriptPath` (`BASH_SOURCE[0]`) está vacío en una tubería, así que `fObtainSourceCode` descarga `cSourceTarballUrl` (rama `main` de `github.com/nipegun/ainonyproxy`). Ejecutado desde una copia del repositorio, usa esa copia.
- Si se pasa a `sh` en lugar de a `bash`, una comprobación POSIX justo después de `set -euo pipefail` lo detiene y muestra la línea de comandos correcta.
- El apt de Debian nunca pregunta nada (`DEBIAN_FRONTEND=noninteractive`, `--force-confdef --force-confold`) y espera hasta 10 minutos a que otro apt suelte su bloqueo (`DPkg::Lock::Timeout=600`).
- `fCleanup` cierra la tubería hacia `tee` y lo espera (5 s como máximo), para que las últimas líneas no aparezcan después del prompt.

### Idiomas de la interfaz

Los textos viven en `frontend/lang/<code>.json` (`en-GB`, `en-US`, `es-AR`, `es-ES`, `fr-FR`). `en-US.json` es la fuente y el marcado lleva el texto en en-US como respaldo, de modo que una clave que falte muestra inglés en lugar del nombre de la clave. `/api/languages` los lista ordenados por código (que es el orden alfabético que piden las reglas) y la elección se recuerda en `localStorage` (`ainonyproxy_lang`).

### Tema claro y tema oscuro

Todas las páginas incluyen `partials/theme-head.html` en su `<head>`. Define cada color como una propiedad personalizada de CSS tres veces: oscuro (`:root`, el predeterminado), claro por preferencia del sistema (`@media (prefers-color-scheme: light)` salvo con `data-theme="dark"`) y claro elegido (`:root[data-theme="light"]`). Ninguna regla de las páginas escribe un color directamente, salvo los degradados y brillos de la marca, que funcionan en los dos temas. Un pequeño script en línea pone `data-theme` en `<html>` a partir de `localStorage` (`ainonyproxy_theme`) antes del primer pintado, de modo que la página nunca muestra un destello del otro tema. Sin una elección guardada no hay `data-theme` y la página sigue el tema del sistema, también cuando cambia con la página abierta. `partials/theme-script.html` dibuja el selector (Sistema / Claro / Oscuro) con `fRenderThemeSwitch` y guarda la elección con `fSetTheme`; el evento `storage` la lleva a las demás pestañas abiertas.

### Páginas sin sesión

`login.html`, `register.html` y `recover.html` extienden `auth-base.html`, que contiene sus estilos, la fila de idiomas, el selector de tema y el script común (`fTranslateOr`, `fErrorTextFromData`, `fIsSafeRedirect`, `fCopyCode`). Cada página define `vPageTitleKey` y `vPageTitleFallback` y rellena los bloques `content` y `scripts`.

---

## 2. Mapa de módulos

| Módulo | Ruta | Responsabilidad | Depende de | Usado por |
|---|---|---|---|---|
| Punto de entrada | `backend/ainonyproxy.py` | Construye `vApp`, el middleware, los routers, los certificados, los puertos, las comprobaciones de arranque y la CLI de usuarios | `config`, todos los `routes/*`, `services.logger`, `services.users`, `services.port_guard` | systemd/OpenRC, `deploy/run.sh`, instaladores |
| Configuración | `backend/config.py` | Rutas bajo `/opt/ainonyproxy/`, modelos Pydantic, carga y guardado de los archivos JSON | `pydantic` | todo |
| Rutas de IA | `backend/routes/chat.py` | `/api/ai/` (listado) y `/api/ai/{provider}` (chat), desenmascarado SSE | `services.decision`, `services.masking`, `services.logger`, `services.dates` | `ainonyproxy.py` |
| Estado | `backend/routes/health.py` | `/api/ai/status` | `services.decision` | `ainonyproxy.py`, instaladores (verificación) |
| Información | `backend/routes/info.py` | `/api/ai/info` | `config`, `services.decision`, `services.pii_detector` | `ainonyproxy.py` |
| Rutas de autenticación | `backend/routes/auth.py` | Páginas `/auth/login/`, `/auth/register/` y `/auth/recover/`, `/api/auth/*`, frenos de fuerza bruta y de registro | `services.auth`, `services.users`, `services.settings`, `routes.users` (`fUserErrorToHttp`) | `ainonyproxy.py` |
| Rutas del panel | `backend/routes/dashboard.py` | `/`, `/admin/dashboard/*`, `/user/dashboard/*`, `/api/admin/logs`, `/api/admin/stats`, `/api/languages*` | `services.auth`, `services.logger`, `config` | `ainonyproxy.py` |
| Rutas de usuarios | `backend/routes/users.py` | `/api/admin/users*`, `/api/admin/registration`, `/api/user/account*` | `services.auth`, `services.users`, `services.settings` | `ainonyproxy.py`, `routes/auth.py` |
| Decisión | `backend/services/decision.py` | `Router`: un `LlmClient` por proveedor, decide si se enmascara | `services.pii_detector`, `services.masking`, `services.llm_client` | `routes/chat.py`, `routes/health.py`, `routes/info.py` |
| Detector de PII | `backend/services/pii_detector.py` | Analiza los mensajes, valida los modelos de spaCy | `presidio.analyzer`, `services.language_detector` | `services.decision`, `ainonyproxy.py`, `routes/info.py` |
| Detector de idioma | `backend/services/language_detector.py` | `langdetect` + idioma de respaldo | `config` | `services.pii_detector` |
| Enmascarado | `backend/services/masking.py` | Enmascarado, desenmascarado, búfer de streaming | `services.pii_detector` (tipos) | `services.decision`, `routes/chat.py` |
| Cliente de LLM | `backend/services/llm_client.py` | HTTP hacia las APIs compatibles con OpenAI y hacia Anthropic, streaming | `httpx` | `services.decision` |
| Registro de peticiones | `backend/services/logger.py` | `request_logs`, estadísticas, limpieza; `fOpenDatabase` | `config`, `services.dates` | `routes/chat.py`, `routes/dashboard.py`, `services.users`, `ainonyproxy.py` |
| Usuarios | `backend/services/users.py` | `users`, `user_sessions`, hash de contraseñas, códigos de recuperación | `services.logger` (`fOpenDatabase`), `services.dates` | `services.auth`, `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Ajustes | `backend/services/settings.py` | `app_settings`: ajustes que se cambian desde el panel (`registration_open`) | `services.logger` (`fOpenDatabase`), `services.dates` | `routes/auth.py`, `routes/users.py`, `ainonyproxy.py` |
| Utilidades de autenticación | `backend/services/auth.py` | Cookie de sesión, usuario actual, guardas, redirección al inicio de sesión | `services.users`, `config` | `routes/auth.py`, `routes/dashboard.py`, `routes/users.py` |
| Fechas | `backend/services/dates.py` | Formatos de fecha de almacenamiento y de visualización | - | `logger`, `users`, `chat`, `view_database.py` |
| Guarda de puertos | `backend/services/port_guard.py` | Libera un puerto TCP a través de `/proc` | - | `ainonyproxy.py` |
| Envoltorio de Presidio | `backend/presidio/analyzer.py` | `AnalyzerEngine` con un modelo de spaCy por idioma | `presidio_analyzer`, `config` | `services.pii_detector` |
| Modelos de spaCy | `backend/presidio/setup.py` | Instala los modelos de spaCy | `pip` | instaladores, `deploy/run.sh` |
| Visor de la base de datos | `backend/view_database.py` | Visor interactivo de la base de datos en la terminal | `config`, `services.dates` | personas |
| Página del panel | `frontend/templates/dashboard.html` | Ambos paneles (Jinja2 + JavaScript puro) | `/api/*` | `routes/dashboard.py` |
| Páginas sin sesión | `frontend/templates/auth-base.html` + `login.html`, `register.html`, `recover.html` | Formularios de inicio de sesión, registro y recuperación de la contraseña | `/api/auth/*`, `/api/languages*` | `routes/auth.py` |
| Tema | `frontend/templates/partials/theme-head.html`, `partials/theme-script.html` | Colores de los dos temas y el selector de tema | - | todas las páginas |
| Textos | `frontend/lang/*.json` | Traducciones de la interfaz | - | todas las páginas |
| Instaladores | `deploy/install-update-reinstall-{debian,alpine}.sh` | Instalar, actualizar, reinstalar | repositorio o tarball de GitHub | root |
| Lanzador manual | `deploy/run.sh` | venv, dependencias, valores por defecto, modelos, arranque en primer plano | `backend/` | personas |

---

## 3. Índice de símbolos clave

| Símbolo | Archivo:línea | Qué hace |
|---|---|---|
| `vApp` | `backend/ainonyproxy.py:288` | La aplicación FastAPI (documentación en `/api/doc/`) |
| `fMain` | `backend/ainonyproxy.py:404` | Punto de entrada: CLI o certificados + puertos + servidores |
| `fRunCommandLine` | `backend/ainonyproxy.py:366` | `--user-exists`, `--list-users`, `--set-user` |
| `fLifespan` | `backend/ainonyproxy.py:242` | Comprobaciones de arranque, primer administrador, banner, tarea de limpieza |
| `fValidateStartup` | `backend/ainonyproxy.py:120` | Inicializa Presidio y se detiene si faltan modelos |
| `fEnsureSelfSignedCertificate` | `backend/ainonyproxy.py:54` | Crea el certificado autofirmado con `openssl` |
| `fCreateRedirectApp` | `backend/ainonyproxy.py:87` | Aplicación HTTP que responde 308 hacia HTTPS |
| `fRequestIdMiddleware` | `backend/ainonyproxy.py:312` | `X-Request-ID` y cabeceras de seguridad |
| `cHomeDir` | `backend/config.py:20` | `/opt/ainonyproxy` (o `AINONYPROXY_HOME`) |
| `AppConfig` | `backend/config.py:111` | Modelo Pydantic raíz de la configuración |
| `fLoadConfig` | `backend/config.py:341` | Lee `config.json` + `api_urls.json` + `api_keys.json` + `pii_detection.json` |
| `fGetConfig` | `backend/config.py:407` | Singleton de la configuración |
| `fEnsureApiKeys` | `backend/config.py:263` | Pide las claves que faltan sólo si hay una terminal |
| `fChatCompletions` | `backend/routes/chat.py:127` | `POST /api/ai/{provider}`: detectar, enmascarar, llamar, desenmascarar, registrar |
| `fCreateLogData` | `backend/routes/chat.py:56` | Construye la fila del registro, obedeciendo `log_content` / `log_masked_content` |
| `fCreateUnmaskedStream` | `backend/routes/chat.py:261` | Desenmascara un flujo SSE |
| `fListProviders` | `backend/routes/chat.py:100` | `GET /api/ai/` |
| `Router.mDecide` | `backend/services/decision.py:55` | Análisis + decisión de enmascarar para una conversación |
| `PiiDetector.mAnalyzeMessages` | `backend/services/pii_detector.py:78` | Analiza el último mensaje del usuario |
| `PiiDetector.mAnalyzeAllMessages` | `backend/services/pii_detector.py:123` | Analiza todos los mensajes user/assistant |
| `PiiDetector.mValidateLanguages` | `backend/services/pii_detector.py:222` | Qué idiomas configurados tienen su modelo |
| `fMask` | `backend/services/masking.py:38` | Sustituye las entidades por marcadores |
| `fUnmaskText` | `backend/services/masking.py:87` | Vuelve a poner los valores originales |
| `fUnmaskStreamFragment` | `backend/services/masking.py:126` | Desenmascarado en streaming con un búfer |
| `LlmClient.mCompleteChat` | `backend/services/llm_client.py:198` | Envía la petición (compatible con OpenAI o Anthropic) |
| `RequestLogger` | `backend/services/logger.py:75` | Tabla `request_logs`, estadísticas, limpieza |
| `fOpenDatabase` | `backend/services/logger.py:49` | Abre SQLite creando su carpeta con permisos 700 |
| `UserStore` | `backend/services/users.py:106` | Usuarios y sesiones |
| `UserStore.mAuthenticate` | `backend/services/users.py:252` | Comprueba las credenciales en tiempo constante |
| `UserStore.mCreateSession` | `backend/services/users.py:331` | Nuevo token de sesión (sólo se guarda su hash) |
| `fHashPassword` | `backend/services/users.py:50` | PBKDF2-SHA256 |
| `UserStore.mNewRecoveryCode` | `backend/services/users.py:273` | Nuevo código de recuperación para un usuario (sólo se guarda su SHA-256) |
| `UserStore.mRecoverPassword` | `backend/services/users.py:288` | Gasta un código de recuperación: nueva contraseña, sesiones cerradas, código nuevo |
| `fGenerateRecoveryCode` | `backend/services/users.py:73` | `XXXXX-XXXXX-XXXXX-XXXXX`, 100 bits aleatorios |
| `SettingsStore` | `backend/services/settings.py:29` | Tabla `app_settings` (ajustes que se cambian desde el panel) |
| `dSettingDefaults` | `backend/services/settings.py:24` | Valor de cada ajuste mientras nadie lo ha cambiado |
| `fGetCurrentUser` | `backend/services/auth.py:27` | Usuario de la cookie de sesión |
| `fRequireApiAdmin` | `backend/services/auth.py:70` | Guarda 401/403 para `/api/admin/*` |
| `fLoginRedirect` | `backend/services/auth.py:54` | 303 a `/auth/login/?next=...` |
| `fIsSafeNextPath` | `backend/services/auth.py:40` | Sólo destinos del mismo sitio después del inicio de sesión |
| `fApiLogin` | `backend/routes/auth.py:137` | `POST /api/auth/login` (freno de fuerza bruta) |
| `fApiRegister` | `backend/routes/auth.py:157` | `POST /api/auth/register` (¿abierto?, freno, usuario, código de recuperación, sesión) |
| `fApiRecover` | `backend/routes/auth.py:188` | `POST /api/auth/recover` (mismo freno de fuerza bruta que el inicio de sesión) |
| `fApiNewRecoveryCode` | `backend/routes/users.py:115` | `POST /api/user/account/recovery-code` |
| `fApiSetRegistration` | `backend/routes/users.py:95` | `PUT /api/admin/registration` |
| `fAdminDashboardTab` | `backend/routes/dashboard.py:75` | Renderiza `/admin/dashboard/<tab>/` |
| `fUserDashboardTab` | `backend/routes/dashboard.py:95` | Renderiza `/user/dashboard/<tab>/` |
| `aAdminTabs` / `aUserTabs` | `backend/routes/dashboard.py:35` | Pestañas de cada panel (la primera es la de por defecto) |
| `fNowStorage` | `backend/services/dates.py:31` | Ahora, en el formato de almacenamiento |
| `fStorageToDisplay` | `backend/services/dates.py:56` | Del formato de almacenamiento al formato de visualización |
| `fFreePort` | `backend/services/port_guard.py:63` | Detiene lo que escucha en un puerto |
| `PiiAnalyzer.mInitialize` | `backend/presidio/analyzer.py:63` | Construye el motor de Presidio con los modelos de spaCy |
| `fEscapeHtml` (JS) | `frontend/templates/dashboard.html`, `auth-base.html` | Escapa todo valor dinámico antes de `innerHTML` |
| `fStorageDateToDisplay` (JS) | `frontend/templates/dashboard.html` | Formato de visualización de fechas en el navegador |
| `fSetTheme` / `fRenderThemeSwitch` (JS) | `frontend/templates/partials/theme-script.html` | Guarda la elección de tema y dibuja el selector |
| Tokens del tema (CSS) | `frontend/templates/partials/theme-head.html` | Colores de los temas oscuro y claro |
| `fCopyCode` (JS) | `frontend/templates/auth-base.html`, `dashboard.html` | Copia un código de recuperación, o lo selecciona si no hay acceso al portapapeles |
| `fRunSteps` (bash) | `deploy/install-update-reinstall-*.sh` | Lista ordenada de los pasos de instalación |
| `fMain` (bash) | `deploy/install-update-reinstall-*.sh` | Registro + ejecuta `fRunSteps` en un bash nuevo |
| `fObtainSourceCode` (bash) | `deploy/install-update-reinstall-*.sh` | El código de la copia local del repositorio, o el tarball de GitHub cuando el script llega por una tubería |
| `fCleanup` (bash) | `deploy/install-update-reinstall-*.sh` | Trampa `EXIT`: borra el código descargado y espera a `tee` |

---

## 4. Flujos principales

### Petición de chat (`POST /api/ai/{provider}`)

1. `fChatCompletions` (`routes/chat.py`) comprueba el proveedor con `Router.mProviderExists` y valida el cuerpo con `ChatRequestSchema`.
2. `Router.mDecide` → `PiiDetector.mAnalyzeMessages` → `LanguageDetector.mDetect` → `PiiDetector.mDetectPii` → `PiiAnalyzer.mAnalyze` (Presidio).
3. Con PII: `Router._mDecideMask` → `PiiDetector.mAnalyzeAllMessages` → `fMaskMessages` → `fMask` para cada mensaje.
4. `Router.mGetClient(provider).mCompleteChat(petición enmascarada)` → `_mCompleteChatJson` / `_mCompleteChatJsonAnthropic` / `_mCompleteChatStreaming` / `_mCompleteChatStreamingAnthropic`.
5. Respuesta JSON: `fUnmaskResponse` → `fLogRequest(fCreateLogData(...))` → `JSONResponse` con las cabeceras `X-Ainonyproxy-*`.
6. Respuesta en streaming: primero `fLogRequest` (sin el texto de la respuesta), después `StreamingResponse(fCreateUnmaskedStream(...))` → `fUnmaskStreamFragment` por cada fragmento → `fFlushStreamBuffer` al final.
7. Errores: proveedor desconocido 404, cuerpo no válido 400, fallo de Presidio 503, fallo del proveedor 502.

### Arranque (`python3 ainonyproxy.py`)

1. `fMain` → `fParseArguments` (las opciones de la CLI terminan aquí) → `fEnsureApiKeys` → `fGetConfig`.
2. Certificado: `fDetectCertificates` → `server.ssl` → `fEnsureSelfSignedCertificate`.
3. `fFreePort(11080)`, `fFreePort(11443)`.
4. Uvicorn (o Hypercorn con `proxy_protocol`) arranca `fCreateRedirectApp(11443)` en 11080 y `vApp` en 11443.
5. `fLifespan` → `fValidateStartup` (Presidio + modelos, termina si falta un modelo) → `fEnsureAdminUser` → `fPrintStartupBanner` → `fPeriodicCleanupTask`.

### Inicio de sesión

1. `GET /admin/dashboard/overview/` sin sesión → `fAdminDashboardTab` → `fLoginRedirect` → `303 /auth/login/?next=%2Fadmin%2Fdashboard%2Foverview%2F`.
2. `fLoginPage` renderiza `login.html` con `vNext` (sólo si `fIsSafeNextPath`).
3. El formulario llama a `POST /api/auth/login` → `fApiLogin` → `UserStore.mAuthenticate` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON con `redirect` (la ruta `next`, o el panel del rol).
4. Cada página o llamada a la API posterior → `fGetCurrentUser` → `UserStore.mGetSessionUser`.

### Registro

1. `GET /auth/register/` → `fRegisterPage` → `register.html` con `vRegistrationOpen` (`SettingsStore.mIsRegistrationOpen`). A un usuario con sesión se le envía a su panel.
2. El formulario llama a `POST /api/auth/register` → `fApiRegister`: 403 `registration_closed`, o 429 tras 5 cuentas por dirección y hora → `UserStore.mCreateUser` (rol `user`) → `UserStore.mNewRecoveryCode` → `UserStore.mCreateSession` → `fSetSessionCookie` → JSON con `recovery_code` y `redirect`.
3. La página muestra el código una vez; «Ir a mi panel» sigue `redirect`.

### Recuperación de la contraseña

1. `GET /auth/recover/` → `fRecoverPage` → `recover.html`.
2. `POST /api/auth/recover` → `fApiRecover` → freno de fuerza bruta (`fRecentFailures`) → `UserStore.mRecoverPassword`: valida la nueva contraseña, compara en tiempo constante el SHA-256 del código y, en un único `UPDATE ... WHERE recovery_code_hash = <hash anterior>`, pone la nueva contraseña y un código nuevo; después borra todas las sesiones del usuario.
3. Usuario o código erróneos → 400 `invalid_recovery_code` y un fallo más. Correctos → JSON con el nuevo `recovery_code`, que se muestra una vez.

### Pestaña del panel

`/admin/dashboard/` → 307 a `/admin/dashboard/overview/` (la primera de `aAdminTabs`). `fAdminDashboardTab` comprueba la sesión y el rol y renderiza `dashboard.html` con `vRole`, `vTab`, `aTabs`. El script de la página lee `data-tab` y carga sólo lo que necesita esa pestaña: `overview` → `/api/admin/stats` + `/api/admin/logs` cada 5 s; `users` → `/api/admin/registration` + `/api/admin/users`; `account` → `/api/user/account`; `api` → `/api/ai/`; `help` → se renderiza en local.

### Instalación (`install-update-reinstall-debian.sh --install`)

`fMain` → `fStartLogging` (tee a `/root/webapp-install.log`) → bash nuevo → `fRunSteps`: `fParseArguments` → `fCheckRoot` → `fCheckDistro` → (`--reinstall`: `fConfirmReinstall` → `fStopService` → `fRemoveInstallation`) → `fInstallDependencies` → `fCheckPythonVersion` → `fCreateAppUser` → `fCreateDirectories` → `fObtainSourceCode` (copia local o tarball de GitHub) → `fStopService` → `fDeploySourceCode` → `fInstallDefaultConfig` → `fBuildVirtualEnv` → `fInstallSpacyModels` → `fGenerateCertificates` → `fInitializeAdminUser` (`ainonyproxy.py --user-exists` / `--set-user --password-stdin`, después `fWriteCredentialsFile`) → `fSetPermissions` → `fInstallService` → `fStartService` (systemd/OpenRC, o un proceso normal en los contenedores que no los tienen) → `fVerifyInstallation` (consulta repetidamente `/api/ai/status`) → `fPrintSummary`.

Al salir, `fCleanup` borra el código descargado y espera a que `tee` escriba las últimas líneas.

---

## 5. Punto de entrada y mapa de rutas

### Web

| Ruta | Handler | Archivo | Acceso |
|---|---|---|---|
| `GET /` | `fRoot` | `backend/routes/dashboard.py` | Redirige al inicio de sesión o al panel del rol |
| `GET /auth/login/` | `fLoginPage` | `backend/routes/auth.py` | Pública |
| `GET /auth/register/` | `fRegisterPage` | `backend/routes/auth.py` | Pública (con el registro cerrado muestra un aviso) |
| `GET /auth/recover/` | `fRecoverPage` | `backend/routes/auth.py` | Pública |
| `GET /admin/dashboard/` | `fAdminDashboardRoot` | `backend/routes/dashboard.py` | admin → 307 a `overview/` |
| `GET /admin/dashboard/{overview,users,account,help}/` | `fAdminDashboardTab` | `backend/routes/dashboard.py` | admin |
| `GET /user/dashboard/` | `fUserDashboardRoot` | `backend/routes/dashboard.py` | cualquier usuario → 307 a `api/` |
| `GET /user/dashboard/{api,account,help}/` | `fUserDashboardTab` | `backend/routes/dashboard.py` | cualquier usuario |
| `GET /api/doc/` | Swagger UI de FastAPI | `backend/ainonyproxy.py` | Pública |
| `GET /api/doc/redoc/` | ReDoc de FastAPI | `backend/ainonyproxy.py` | Pública |
| `GET /api/doc/openapi.json` | FastAPI | `backend/ainonyproxy.py` | Pública |
| `GET /api/ai/` | `fListProviders` | `backend/routes/chat.py` | Pública |
| `POST /api/ai/{provider}` | `fChatCompletions` | `backend/routes/chat.py` | Pública |
| `GET /api/ai/status` | `fStatus` | `backend/routes/health.py` | Pública |
| `GET /api/ai/info` | `fInfo` | `backend/routes/info.py` | Pública |
| `POST /api/auth/login` | `fApiLogin` | `backend/routes/auth.py` | Pública |
| `POST /api/auth/register` | `fApiRegister` | `backend/routes/auth.py` | Pública, mientras el registro esté abierto |
| `POST /api/auth/recover` | `fApiRecover` | `backend/routes/auth.py` | Pública |
| `POST /api/auth/logout` | `fApiLogout` | `backend/routes/auth.py` | Pública |
| `GET /api/auth/session` | `fApiSession` | `backend/routes/auth.py` | cualquier usuario |
| `GET /api/admin/logs?limit=&offset=` | `fApiLogs` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/stats` | `fApiStats` | `backend/routes/dashboard.py` | admin |
| `GET /api/admin/users` | `fApiListUsers` | `backend/routes/users.py` | admin |
| `POST /api/admin/users` | `fApiCreateUser` | `backend/routes/users.py` | admin |
| `GET /api/admin/registration` | `fApiGetRegistration` | `backend/routes/users.py` | admin |
| `PUT /api/admin/registration` | `fApiSetRegistration` | `backend/routes/users.py` | admin |
| `DELETE /api/admin/users/{username}` | `fApiDeleteUser` | `backend/routes/users.py` | admin |
| `PUT /api/admin/users/{username}/password` | `fApiResetPassword` | `backend/routes/users.py` | admin |
| `GET /api/user/account` | `fApiAccount` | `backend/routes/users.py` | cualquier usuario |
| `PUT /api/user/account/password` | `fApiChangePassword` | `backend/routes/users.py` | cualquier usuario |
| `POST /api/user/account/recovery-code` | `fApiNewRecoveryCode` | `backend/routes/users.py` | cualquier usuario |
| `GET /api/languages` | `fApiLanguages` | `backend/routes/dashboard.py` | Pública |
| `GET /api/languages/{code}` | `fApiLanguageFile` | `backend/routes/dashboard.py` | Pública |
| `http://*:11080/*` | `fRedirectToHttps` | `backend/ainonyproxy.py` | 308 a HTTPS |

### Línea de comandos

| Comando | Handler | Archivo |
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

## 6. Análisis de impacto

| Si cambias... | Afecta a... |
|---|---|
| Las rutas de `config.py` (`cHomeDir` y compañía) | Los instaladores (las mismas rutas escritas a mano en sus constantes), `deploy/run.sh`, las unidades de systemd/OpenRC, todos los documentos que nombran `/opt/ainonyproxy/` |
| `AppConfig` y sus submodelos | `backend/config-defaults/config.json`, `fSaveConfig`, el MANUAL (referencia de configuración) |
| El formato de `api_urls.json` / `api_keys.json` | `fLoadConfig`, `fEnsureApiKeys`, `fValidateApiKeys`, los instaladores (`fInstallDefaultConfig`) |
| Los formatos de `services/dates.py` | Todas las fechas almacenadas (`request_logs`, `users`, `user_sessions`), las comparaciones de cadenas de las estadísticas, la limpieza y la caducidad de las sesiones, `fStorageDateToDisplay` en el panel, `view_database.py` |
| Las columnas de `request_logs` | `RequestRecord`, `RequestLogData`, `mRecord`, `fCreateLogData`, los consumidores de `fApiLogs` en `dashboard.html`, `view_database.py` |
| Las tablas `users` / `user_sessions` | `UserStore` (su `_mInitializeDatabase` añade las columnas que falten en bases de datos antiguas), `view_database.py` (opciones 1 y 3), los instaladores (`--user-exists`, `--set-user`) |
| `MaskingContext` o el formato de marcador `<TYPE_N>` | `fMask`, `fUnmaskText`, `fUnmaskStreamFragment` (busca `<` y `>`), la expresión regular que resalta los marcadores en `dashboard.html` |
| Los campos de `PiiDetectionResult` | `Router`, `fCreateLogData`, las cabeceras de respuesta de `fChatCompletions` |
| Los tipos de retorno de `LlmClient` | `fChatCompletions` (`is_streaming`, `response`, `model`) |
| La cookie de sesión (`services/auth.py`) | Todas las páginas y APIs protegidas, `login.html` y `register.html` (inicia la sesión del nuevo usuario), `fApi` en `dashboard.html` (redirección en caso de 401) |
| `aAdminTabs` / `aUserTabs` | La barra lateral de `dashboard.html`, las claves `tabs.*` de todos los `frontend/lang/*.json`, el MANUAL |
| El formato del código de recuperación (`cRecoveryCode*`, `fNormalizeRecoveryCode`) | Todos los códigos guardados (un formato nuevo debe seguir aceptando los antiguos, o los usuarios tendrán que generar otros), el marcador de `recover.html`, el MANUAL |
| `app_settings` / `dSettingDefaults` | `SettingsStore`, `/api/admin/registration`, la pestaña Usuarios, `register.html` y `login.html` (enlace al registro) |
| Los tokens del tema (`partials/theme-head.html`) | Todas las páginas. Cada token se define tres veces (oscuro, claro por preferencia del sistema, claro elegido) y los tres bloques deben tener los mismos nombres |
| Una clave de `en-US.json` | La misma clave en `en-GB`, `es-AR`, `es-ES`, `fr-FR` |
| Los puertos 11080 / 11443 | `config-defaults/config.json`, `fVerifyInstallation` y `fPrintSummary` en los instaladores, los textos de ayuda (`help.endpointCode`), el README, el MANUAL |
| Las opciones de la CLI de `ainonyproxy.py` | `fInitializeAdminUser` en ambos instaladores, el MANUAL (restablecer una contraseña) |
| `cSourceTarballUrl`, el repositorio o su rama `main` | Los dos instaladores (cabecera, `fObtainSourceCode`, la comprobación de `sh`), las líneas de instalación de todos los README y MANUAL |

---

## 7. Puntos de extensión

### Un nuevo proveedor de LLM

- Compatible con OpenAI: añade `"name": {"url": "https://.../v1/chat/completions"}` a `/opt/ainonyproxy/config/api_urls.json` (y a `backend/config-defaults/api_urls.json` para las instalaciones nuevas), añade su clave a `api_keys.json` y reinicia. Se sirve en `/api/ai/name`.
- Otro formato de comunicación: añade el valor a `cApiFormat` (`config.py`), detéctalo en `fDetectFormat` y añade una rama en `LlmClient.mCompleteChat` que convierta la petición y la respuesta a la forma de OpenAI (mira la rama de Anthropic: `_mBuildAnthropicBody`, `_mFormatAnthropicResponse`, `_mCompleteChatStreamingAnthropic`). `gemini` está declarado pero todavía no tiene rama: se envía como compatible con OpenAI.

### Un nuevo endpoint de la API

1. Añade la función al router de su audiencia: `vAdminApiRouter` / `vAdminUsersRouter` (`/api/admin`), `vUserAccountRouter` (`/api/user`), `vChatRouter` (`/api/ai`), o un nuevo `APIRouter(tags=[...])` incluido en `ainonyproxy.py` con un prefijo bajo `/api/`.
2. Protégelo con `fRequireApiAdmin(pRequest)` o `fRequireApiUser(pRequest)`.
3. Dale un `summary`: aparece solo en `/api/doc/`.
4. Añade su fila a la sección 5 de todos los archivos CODE.

### Una nueva pestaña del panel

1. Añade su nombre a `aAdminTabs` o a `aUserTabs` (`routes/dashboard.py`).
2. Añade su icono a `dTabIcons`, su bloque `{% if vTab == "name" %}` a `dashboard.html` y su cargador al bloque de inicio del script.
3. Añade `tabs.name` (y sus textos) a todos los `frontend/lang/*.json`.
4. Queda accesible de inmediato en `/admin/dashboard/name/` o en `/user/dashboard/name/`.

### Un nuevo idioma de la interfaz

Copia `frontend/lang/en-US.json` a `frontend/lang/xx-YY.json`, cambia `meta` y traduce los valores. Aparece solo en el selector.

### Un ajuste nuevo del panel

Añade su clave y su valor por defecto a `dSettingDefaults` (`services/settings.py`) con un par de métodos como `mIsRegistrationOpen` / `mSetRegistrationOpen`, un endpoint de administración como `fApiSetRegistration` bajo `/api/admin/` y su control en la pestaña a la que pertenezca (con sus textos en todos los `frontend/lang/*.json`).

### Un color nuevo

Añade la propiedad personalizada a los tres bloques de `partials/theme-head.html` (oscuro, claro por preferencia del sistema, claro elegido) y úsala con `var(--nombre)`. Nunca escribas un color directamente en una página.

### Un nuevo idioma de PII

Añade su código a `languages` en `/opt/ainonyproxy/config/pii_detection.json` (tiene que estar en `cSupportedLanguages`), después ejecuta `presidio/setup.py --languages xx` con el Python del venv (o ejecuta el instalador con `--update`) y reinicia.
