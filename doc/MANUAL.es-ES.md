# ainonyproxy - MANUAL

Este MANUAL también está disponible en:\
[en-GB](MANUAL.en-GB.md), [en-US](MANUAL.md), [es-AR](MANUAL.es-AR.md), es-ES, [fr-FR](MANUAL.fr-FR.md)

Cómo instalar ainonyproxy, configurarlo y usarlo en el día a día.

## Contenido

1. [Qué hace](#qué-hace)
2. [Dónde funciona](#dónde-funciona)
3. [Instalación](#instalación)
4. [Actualizar y reinstalar](#actualizar-y-reinstalar)
5. [Abrirlo](#abrirlo)
6. [Iniciar sesión](#iniciar-sesión)
7. [El panel de administración](#el-panel-de-administración)
8. [El panel de usuario](#el-panel-de-usuario)
9. [Tema claro y tema oscuro](#tema-claro-y-tema-oscuro)
10. [Enviar peticiones a través de ainonyproxy](#enviar-peticiones-a-través-de-ainonyproxy)
11. [Proveedores y claves de API](#proveedores-y-claves-de-api)
12. [Detección de PII](#detección-de-pii)
13. [Lo que se escribe en la base de datos](#lo-que-se-escribe-en-la-base-de-datos)
14. [Referencia de configuración](#referencia-de-configuración)
15. [Archivos y carpetas](#archivos-y-carpetas)
16. [Certificados](#certificados)
17. [Ejecutarlo sin el servicio](#ejecutarlo-sin-el-servicio)
18. [Mirar dentro de la base de datos](#mirar-dentro-de-la-base-de-datos)
19. [Solución de problemas](#solución-de-problemas)
20. [Desinstalar](#desinstalar)

---

## Qué hace

ainonyproxy es un proxy de privacidad para modelos de lenguaje (LLM). Tus aplicaciones envían sus peticiones de chat a ainonyproxy en lugar de enviarlas a OpenAI, Anthropic, DeepSeek, un Ollama local, etc. Con cada petición, ainonyproxy:

1. Detecta la información personal (nombres, direcciones de correo electrónico, números de teléfono, IBAN, direcciones IP, lugares, números de identificación...) con [Presidio](https://microsoft.github.io/presidio/) y spaCy, que se ejecutan en tu propio ordenador.
2. Sustituye cada dato personal por un marcador como `<PERSON_1>` o `<EMAIL_ADDRESS_1>`.
3. Envía la conversación enmascarada al proveedor que hayas elegido.
4. Vuelve a poner los valores reales en la respuesta antes de devolvérsela a tu aplicación.

El proveedor nunca ve los datos personales y tu aplicación no nota nada: habla la API de chat de OpenAI, con o sin streaming.

También tiene un panel web, con tema claro y tema oscuro, que muestra estadísticas y las últimas peticiones y gestiona los usuarios (que pueden crearse su propia cuenta y recuperar la contraseña por su cuenta).

## Dónde funciona

| | |
|---|---|
| Sistema operativo | Debian 13 (trixie) o posterior, o Alpine Linux con un paquete `python3` de la versión 3.13 o posterior |
| Python | 3.13 o posterior (el instalador lo comprueba) |
| Disco | Unos 3 GB (paquetes de Python y modelos de idioma de spaCy) |
| Memoria | 2 GB o más (cada modelo de idioma de spaCy se carga en memoria) |
| Red | Acceso a los proveedores de LLM que uses, y a PyPI y a GitHub durante la instalación |
| Puertos | `11080` (HTTP, sólo redirige) y `11443` (HTTPS) |

Está pensado para usarse desde el mismo ordenador en el que se ejecuta: tus aplicaciones hablan con `https://localhost:11443`.

## Instalación

Ejecuta el instalador como `root`. Lo hace todo solo y no pregunta nada.

**Debian** (una Debian mínima, como la imagen de Docker, no trae curl, así que la línea lo instala primero):

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --install
```

**Alpine Linux** (no trae bash por defecto, así que la línea lo instala primero):

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install
```

También puedes ejecutarlo desde una copia del repositorio: `bash deploy/install-update-reinstall-debian.sh --install`. En ese caso usa el código de esa copia en lugar de descargarlo.

Puedes volver a ejecutarlo sin miedo: los instaladores son idempotentes, así que ejecutar uno dos veces con la misma opción deja el sistema igual que ejecutarlo una sola vez. Están hechos para descargarse con `curl` y pasarse directamente a `bash`: no se ejecuta nada hasta que ha llegado el script entero, así que una descarga cortada a medias no hace nada. Pásalos a `bash`, no a `sh`: con `sh` se detienen y te lo avisan.

### Qué hace el instalador

1. Instala los paquetes del sistema que necesita (Python, compilador, OpenSSL, curl...).
2. Comprueba que Python sea 3.13 o posterior.
3. Crea el usuario de sistema `ainonyproxy` (sin contraseña y sin shell de inicio de sesión), cuyo directorio personal es `/opt/ainonyproxy/`.
4. Copia el código a `/opt/ainonyproxy/webapp/` y crea el entorno virtual de Python en `/opt/ainonyproxy/venv/`.
5. Copia la configuración por defecto a `/opt/ainonyproxy/config/` (sólo los archivos que todavía no existen: nunca sobrescribe los tuyos).
6. Instala los modelos de spaCy de los idiomas configurados en `pii_detection.json`.
7. Crea un certificado autofirmado cuando no hay ningún certificado de Let's Encrypt.
8. Crea el administrador del panel `admin` con una contraseña aleatoria (sólo la primera vez).
9. Instala e inicia el servicio (`systemd` en Debian, `OpenRC` en Alpine) y espera a que responda.

La primera instalación tarda varios minutos: los paquetes de Python y los modelos de spaCy son grandes. En Alpine puede que haya que compilar algunos paquetes, lo que tarda más.

### Dónde está la contraseña

| Archivo | Contenido |
|---|---|
| `/root/webapp-credentials.txt` | El usuario y la contraseña del administrador del panel |
| `/root/webapp-install.log` | Todo lo que hizo el instalador, con la salida de cada comando |

Sólo root puede leer ambos (permisos `600`).

### En contenedores

En un contenedor sin systemd (Docker), el instalador inicia ainonyproxy como un proceso normal en segundo plano y te avisa de que no arrancará por sí solo después de reiniciar el contenedor: vuelve a ejecutar el instalador para iniciarlo. En Alpine prepara OpenRC para que el servicio pueda ejecutarse dentro del contenedor.

## Actualizar y reinstalar

| Comando | Qué hace |
|---|---|
| `--install` | Instala. En una instalación existente se comporta como `--update`. |
| `--update` | Reemplaza el código y actualiza las dependencias y los modelos. Conserva la configuración, la base de datos, los usuarios, los certificados y las contraseñas. |
| `--reinstall` | Elimina el código, el entorno virtual, la configuración, la base de datos y los registros (**no** los certificados) y vuelve a instalar desde cero, con una nueva contraseña de administrador. Pide confirmación; añade `--yes` para saltarte la pregunta. |

```bash
curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --update
```

## Abrirlo

| Qué | Dirección |
|---|---|
| Panel | `https://localhost:11443/` (te lleva al inicio de sesión) |
| Inicio de sesión | `https://localhost:11443/auth/login/` |
| Crear una cuenta | `https://localhost:11443/auth/register/` (cuando el registro está abierto) |
| Recuperar la contraseña | `https://localhost:11443/auth/recover/` |
| API de IA | `https://localhost:11443/api/ai/{provider}` |
| Documentación de la API (Swagger) | `https://localhost:11443/api/doc/` |
| Estado | `https://localhost:11443/api/ai/status` |

Todo lo que llegue a `http://...:11080` se redirige de forma permanente a la misma dirección en `https://...:11443`.

Con el certificado autofirmado, el navegador muestra una advertencia la primera vez: es lo esperado, la conexión va cifrada de todos modos. Consulta [Certificados](#certificados) para usar uno real.

## Iniciar sesión

Abre el panel e inicia sesión con el usuario y la contraseña de `/root/webapp-credentials.txt`. Si abres la dirección de un panel sin haber iniciado sesión, se te envía al inicio de sesión y, después de iniciarla, de vuelta a la página que pediste.

Hay dos roles:

| Rol | Qué puede hacer |
|---|---|
| `admin` | Todo: ambos paneles, las estadísticas, los registros de peticiones y la gestión de usuarios |
| `user` | El panel de usuario: datos de conexión de la API y su propia contraseña |

Una sesión dura 12 horas (`dashboard.session_hours`). Tras 5 intentos fallidos desde la misma dirección, el inicio de sesión queda bloqueado durante 15 minutos.

### Crear una cuenta

Cuando el registro está abierto, cualquiera que llegue al inicio de sesión puede crearse una cuenta en `/auth/register/` (enlace «Crear una cuenta» del inicio de sesión). Estas cuentas tienen siempre el rol `user`: solo un administrador puede hacer `admin` a alguien. El registro está abierto por defecto, y un administrador lo abre o lo cierra en **Usuarios → Registro**. Una misma dirección puede crear hasta 5 cuentas por hora.

Justo después de crear la cuenta, la página muestra una única vez su código de recuperación. Cuando confirmas que lo has guardado, «Ir a mi panel» abre el panel de usuario con la sesión ya iniciada.

### Códigos de recuperación

Cada cuenta puede tener un código de recuperación, como `ABCDE-FGHJK-LMNPQ-RSTUV`, para establecer una nueva contraseña sin un administrador. Solo se muestra una vez: ainonyproxy guarda únicamente su huella (SHA-256), así que nadie puede volver a mostrarlo. Cópialo o apúntalo y guárdalo en un lugar seguro.

| Cuándo | Quién ve el código |
|---|---|
| Te creas la cuenta en `/auth/register/` | Tú |
| Un administrador crea tu usuario en **Usuarios** | El administrador, que te lo entrega |
| Pulsas **Generar un nuevo código de recuperación** en **Cuenta** (pide tu contraseña actual) | Tú. El código anterior deja de funcionar. |
| Lo usas en `/auth/recover/` | Recibes uno nuevo: cada código sirve una sola vez |

El administrador que crea el instalador y los usuarios creados desde la terminal empiezan sin código: genera uno en **Cuenta**.

### Si olvidas tu contraseña

Abre `/auth/recover/` (enlace «¿Has olvidado tu contraseña?» del inicio de sesión) y escribe tu usuario, tu código de recuperación (con o sin guiones, en mayúsculas o minúsculas) y dos veces la nueva contraseña. La contraseña cambia, se cierran todas las sesiones de la cuenta y la página muestra tu nuevo código de recuperación. Los intentos erróneos cuentan como inicios de sesión fallidos: tras 5 desde la misma dirección, hay que esperar 15 minutos.

Sin código de recuperación, un administrador puede asignarte una nueva contraseña en **Usuarios**, y root puede hacerlo desde la terminal del servidor (sección siguiente).

### Restablecer una contraseña desde la terminal

Si ya nadie puede iniciar sesión, establece una nueva contraseña desde el servidor como root:

```bash
printf '%s\n' 'TheNewPassword' | AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/ainonyproxy.py --set-user admin --role admin --password-stdin
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/db
```

El mismo comando crea el usuario cuando no existe. `--list-users` lista los usuarios. Las contraseñas necesitan al menos 8 caracteres.

## El panel de administración

`/admin/dashboard/` abre la pestaña **Resumen**. Cada pestaña tiene su propia dirección, así que puedes guardarla en marcadores o abrirla directamente.

| Pestaña | Dirección | Qué contiene |
|---|---|---|
| Resumen | `/admin/dashboard/overview/` | Total de peticiones, peticiones con PII enmascarada, tiempo medio de análisis, peticiones de la última hora, los tipos de entidad PII más detectados y las últimas 50 peticiones. Se actualiza cada 5 segundos. Haz clic en una petición para ver su contenido enmascarado (cuando está registrado). |
| Usuarios | `/admin/dashboard/users/` | Abre o cierra el registro en `/auth/register/`. Crea usuarios (nombre, contraseña, rol): el código de recuperación del nuevo usuario se muestra una vez para que se lo entregues. Asígnales una nueva contraseña o elimínalos. No se puede eliminar al último administrador ni a tu propio usuario. |
| Cuenta | `/admin/dashboard/account/` | Tus datos, el formulario para cambiar tu contraseña (al cambiarla se cierran tus otras sesiones) y el de generar un nuevo código de recuperación. |
| Ayuda | `/admin/dashboard/help/` | Un resumen de cómo usar ainonyproxy. |

La barra lateral también tiene un enlace al panel de usuario, el botón para cerrar sesión, el selector de tema (consulta [Tema claro y tema oscuro](#tema-claro-y-tema-oscuro)) y el selector de idioma (en-GB, en-US, es-AR, es-ES, fr-FR). Todas las horas se muestran en UTC con el formato `2026/10/29@13:59:59.723`.

## El panel de usuario

`/user/dashboard/` abre la pestaña **API**.

| Pestaña | Dirección | Qué contiene |
|---|---|---|
| API | `/user/dashboard/api/` | La URL base, un ejemplo con `curl` y la tabla de proveedores disponibles con su endpoint. |
| Cuenta | `/user/dashboard/account/` | Tus datos, el formulario para cambiar tu contraseña y el de generar un nuevo código de recuperación. |
| Ayuda | `/user/dashboard/help/` | Un resumen de cómo usar ainonyproxy. |

## Tema claro y tema oscuro

Todas las páginas (inicio de sesión, registro, recuperación de la contraseña y los dos paneles) tienen un tema claro y uno oscuro. El selector de tema está al pie de la barra lateral de los paneles y debajo de la tarjeta de las páginas de inicio de sesión. Tiene tres botones:

| Botón | Tema |
|---|---|
| Sistema (icono de pantalla) | El tema de tu sistema operativo. Es el predeterminado, y la página cambia sola cuando cambia el del sistema. |
| Claro (icono de sol) | Siempre claro. |
| Oscuro (icono de luna) | Siempre oscuro. |

La elección se recuerda en este navegador (`localStorage`, clave `ainonyproxy_theme`) y se aplica a todas las páginas de ainonyproxy abiertas en él.

## Enviar peticiones a través de ainonyproxy

Apunta tu aplicación a `https://localhost:11443/api/ai/{provider}` en lugar de a la URL del proveedor y envía la misma petición de chat al estilo OpenAI:

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

El proveedor recibe `Write an e-mail to <PERSON_1>, his address is <EMAIL_ADDRESS_1>` y tu aplicación recibe la respuesta con el nombre y la dirección reales de nuevo en su sitio.

- `-k` le dice a curl que acepte el certificado autofirmado. Otros clientes tienen una opción parecida, o puedes instalar el certificado como de confianza.
- Añade `"stream": true` para usar streaming (Server-Sent Events, como OpenAI).
- `messages` acepta los roles `system`, `user` y `assistant`, con contenido de texto.
- Los demás campos (`temperature`, `max_tokens`, `stop`...) se pasan al proveedor. Para Anthropic se convierten a su formato.
- `GET /api/ai/` lista los proveedores con su URL completa.

### Cabeceras de la respuesta

| Cabecera | Significado |
|---|---|
| `X-Ainonyproxy-Provider` | Proveedor usado |
| `X-Ainonyproxy-PII-Detected` | `true` cuando el último mensaje del usuario tenía PII |
| `X-Ainonyproxy-PII-Masked` | `true` cuando la conversación se enmascaró |
| `X-Ainonyproxy-Language` | Idioma usado para la detección |
| `X-Ainonyproxy-Language-Fallback` | `true` cuando el idioma detectado no estaba configurado y se usó el de respaldo |
| `X-Request-ID` | Identificador de la petición (el tuyo, si enviaste uno) |

### Errores

| Código | Cuándo |
|---|---|
| `400` | El cuerpo no es una petición de chat válida |
| `404` | El proveedor no existe |
| `502` | El proveedor respondió con un error o no se pudo contactar con él |
| `503` | La detección de PII no está disponible |

## Proveedores y claves de API

Los proveedores están en `/opt/ainonyproxy/config/api_urls.json`:

```json
{
  "openai": { "url": "https://api.openai.com/v1/chat/completions" },
  "anthropic": { "url": "https://api.anthropic.com/v1/messages" },
  "ollama": { "url": "http://localhost:11434/v1/chat/completions" }
}
```

Cada entrada puede llevar también `"format"` (`openai` o `anthropic`; se deduce de la URL cuando falta) y `"model"` (un modelo que se usa siempre, pida lo que pida el cliente). El nombre de la entrada es el nombre que va en la URL: `/api/ai/openai`.

Las claves están en `/opt/ainonyproxy/config/api_keys.json`, aparte del resto para que sólo ese archivo contenga los secretos:

```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-...",
  "ollama": ""
}
```

Los proveedores locales (`localhost`, `10.x`, `172.16-31.x`, `192.168.x`) pueden tener la clave vacía. Los valores pueden usar variables de entorno: `"${OPENAI_API_KEY}"`.

Después de editar cualquiera de los dos archivos, conserva el propietario y reinicia:

```bash
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/config/*.json
chmod 600 /opt/ainonyproxy/config/*.json
systemctl restart ainonyproxy        # Debian
rc-service ainonyproxy restart       # Alpine
```

Incluidos por defecto: `anthropic`, `deepseek`, `gemini`, `kimi`, `llamacpp`, `ollama`, `openai`, `openrouter`, `vllm` y `zai`. `gemini` está declarado pero se envía como compatible con OpenAI, que la API nativa de Gemini no entiende; y `llamacpp` apunta a `/completion`, que no es un endpoint de chat. Usa la URL compatible con OpenAI de esos servidores si los necesitas.

## Detección de PII

Se configura en `/opt/ainonyproxy/config/pii_detection.json`:

| Clave | Significado | Por defecto |
|---|---|---|
| `languages` | Idiomas que detectar (códigos de spaCy: `en`, `es`, `fr`, `de`, `it`, `pt`, `ca`...) | `["es", "en"]` |
| `fallback_language` | Idioma que se usa cuando el detectado no está en la lista | `es` |
| `score_threshold` | Confianza mínima (de 0 a 1) para considerar algo como PII. Si es más baja encuentra más cosas, pero también más falsos positivos. | `0.5` |
| `entities` | Tipos de entidad de Presidio que buscar | Una lista amplia (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN_CODE`, `ES_NIF`...) |

Cada idioma necesita su modelo de spaCy. Después de añadir uno, instala su modelo y reinicia:

```bash
/opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/presidio/setup.py --languages fr
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/venv
systemctl restart ainonyproxy
```

O ejecuta el instalador con `--update`, que instala los modelos de todos los idiomas configurados. ainonyproxy se niega a arrancar cuando un idioma configurado no tiene modelo, para no dejar pasar datos personales por error.

Sólo el último mensaje del usuario decide si una conversación tiene PII. Cuando la tiene, se enmascaran todos los mensajes del usuario y del asistente, y el mismo valor recibe siempre el mismo marcador.

## Lo que se escribe en la base de datos

Cada petición se registra en `/opt/ainonyproxy/db/ainonyproxy.db`: hora, proveedor, modelo, si tenía PII, tipos de entidad, idioma, tiempos y tokens. Que también se registren los textos depende de `config.json`:

| Clave | Qué controla | Por defecto |
|---|---|---|
| `logging.log_content` | La petición original y la respuesta al cliente (con los datos personales reales) | `false` |
| `logging.log_masked_content` | La petición enmascarada y la respuesta del proveedor (con marcadores) | `true` |
| `logging.retention_days` | Días que se conserva una petición; `0` las conserva para siempre | `30` |

Con los valores por defecto, la base de datos nunca contiene los datos personales en sí.

La misma base de datos guarda los usuarios del panel (solo las huellas de sus contraseñas y de sus códigos de recuperación, nunca los valores), sus sesiones (solo la huella de cada token) y los ajustes que un administrador cambia desde el panel (tabla `app_settings`, como si el registro está abierto).

## Referencia de configuración

`/opt/ainonyproxy/config/config.json`:

| Clave | Significado | Por defecto |
|---|---|---|
| `mode` | Sólo existe `mask` | `mask` |
| `server.host` | Dirección en la que escuchar | `0.0.0.0` |
| `server.port` | Puerto HTTP (sólo redirige a HTTPS) | `11080` |
| `server.ssl_port` | Puerto HTTPS | `11443` |
| `server.proxy_protocol` | Espera el protocolo PROXY en HTTPS (para un HAProxy por delante con `send-proxy`) | `false` |
| `server.ssl.enabled` / `certfile` / `keyfile` | Certificado propio, que se usa cuando no hay ningún certificado de Let's Encrypt en la carpeta de certificados | `false` |
| `masking.show_markers` | Pone `marker_text` delante de cada valor desenmascarado en las respuestas | `false` |
| `masking.marker_text` | Texto que usa `show_markers` | `[protected]` |
| `logging.*` | Consulta [Lo que se escribe en la base de datos](#lo-que-se-escribe-en-la-base-de-datos) | |
| `logging.database` | Ruta de la base de datos SQLite | `/opt/ainonyproxy/db/ainonyproxy.db` |
| `dashboard.enabled` | Reservada; el panel siempre está disponible | `true` |
| `dashboard.session_hours` | Duración de una sesión del panel | `12` |
| `ui.default_language` | Idioma de la interfaz para quien no haya elegido uno | `en-US` |

Reinicia el servicio después de cambiarla.

## Archivos y carpetas

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

Todo pertenece al usuario `ainonyproxy`. Sólo él (y root) puede leer `config/`, `db/` y `certificates/`.

## Certificados

Sin nada más, ainonyproxy sirve HTTPS con un certificado autofirmado (`/opt/ainonyproxy/certificates/selfsigned-fullchain.pem`), válido para `localhost`, `127.0.0.1` y el nombre de la máquina.

Para usar un certificado de Let's Encrypt, copia sus dos archivos a la carpeta de certificados con estos nombres y reinicia:

```bash
cp /etc/letsencrypt/live/your.domain/fullchain.pem /opt/ainonyproxy/certificates/fullchain.pem
cp /etc/letsencrypt/live/your.domain/privkey.pem /opt/ainonyproxy/certificates/privkey.pem
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/certificates/*.pem
chmod 600 /opt/ainonyproxy/certificates/privkey.pem
systemctl restart ainonyproxy
```

Tienen prioridad sobre todo lo demás. Repite la copia después de cada renovación.

## Ejecutarlo sin el servicio

`deploy/run.sh` (en una copia del repositorio) crea el entorno virtual, instala lo que falta e inicia ainonyproxy en primer plano, mostrando todo lo que hace. Detenlo con `Ctrl+C`.

```bash
bash deploy/run.sh                                   # as root, uses /opt/ainonyproxy
AINONYPROXY_HOME="$PWD/_/temp/home" bash deploy/run.sh   # as any user, in a folder of your own
```

Si el servicio instalado se está ejecutando, deténlo primero: ambos usan los mismos puertos (ainonyproxy detiene lo que siga escuchando en ellos antes de arrancar).

Cuando todavía no hay usuarios (nunca se instaló), el primer arranque crea `admin` e imprime su contraseña una única vez en la terminal.

## Mirar dentro de la base de datos

```bash
AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/view_database.py
```

Un menú muestra los usuarios, las sesiones, las últimas peticiones, el detalle de una petición, los contenidos enmascarados y las estadísticas generales.

## Solución de problemas

| Qué ocurre | Qué hacer |
|---|---|
| El servicio no arranca | `journalctl -u ainonyproxy -n 100 --no-pager` (Debian) o `/opt/ainonyproxy/logs/ainonyproxy.log` (Alpine y contenedores). |
| "Missing spaCy models" | Instala los modelos de los idiomas configurados (consulta [Detección de PII](#detección-de-pii)) o ejecuta el instalador con `--update`. |
| Un proveedor responde 502 | Revisa su URL en `api_urls.json` y su clave en `api_keys.json`. El detalle del error va en la respuesta. |
| "Remote providers without an API key" al arrancar | Añade sus claves a `api_keys.json`, o ignóralo para los proveedores que no uses. |
| El navegador advierte del certificado | Es lo esperado con el certificado autofirmado. Consulta [Certificados](#certificados). |
| "Demasiados intentos fallidos" | Espera 15 minutos o reinicia el servicio. |
| Nadie recuerda la contraseña de admin | Consulta [Restablecer una contraseña desde la terminal](#restablecer-una-contraseña-desde-la-terminal). |
| «El registro está cerrado» | Un administrador lo abre en **Usuarios → Registro**, o te crea la cuenta. |
| Has perdido el código de recuperación | Mientras puedas iniciar sesión, genera uno nuevo en **Cuenta → Código de recuperación**. Si no puedes iniciar sesión, un administrador te asigna una nueva contraseña en **Usuarios**. |
| El primer arranque tarda mucho | Cargar los modelos de spaCy tarda desde varios segundos hasta un minuto; el instalador espera hasta 3 minutos. |

## Desinstalar

Como root:

```bash
systemctl disable --now ainonyproxy && rm -f /etc/systemd/system/ainonyproxy.service && systemctl daemon-reload   # Debian
rc-service ainonyproxy stop; rc-update del ainonyproxy default; rm -f /etc/init.d/ainonyproxy                     # Alpine
rm -rf /opt/ainonyproxy
userdel ainonyproxy     # Debian (on Alpine: deluser ainonyproxy)
rm -f /root/webapp-credentials.txt /root/webapp-install.log
```
