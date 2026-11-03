# ainonyproxy - MANUAL

Este MANUAL también está disponible en:\
[en-GB](MANUAL.en-GB.md), [en-US](MANUAL.md), es-AR, [es-ES](MANUAL.es-ES.md), [fr-FR](MANUAL.fr-FR.md)

Cómo instalar ainonyproxy, configurarlo y usarlo en el día a día.

## Contenido

1. [Qué hace](#qué-hace)
2. [Dónde corre](#dónde-corre)
3. [Instalación](#instalación)
4. [Actualización y reinstalación](#actualización-y-reinstalación)
5. [Cómo abrirlo](#cómo-abrirlo)
6. [Iniciar sesión](#iniciar-sesión)
7. [El panel de administración](#el-panel-de-administración)
8. [El panel de usuario](#el-panel-de-usuario)
9. [Tema claro y tema oscuro](#tema-claro-y-tema-oscuro)
10. [Enviar solicitudes a través de ainonyproxy](#enviar-solicitudes-a-través-de-ainonyproxy)
11. [Proveedores y claves de API](#proveedores-y-claves-de-api)
12. [Detección de PII](#detección-de-pii)
13. [Qué se escribe en la base de datos](#qué-se-escribe-en-la-base-de-datos)
14. [Referencia de configuración](#referencia-de-configuración)
15. [Archivos y carpetas](#archivos-y-carpetas)
16. [Certificados](#certificados)
17. [Ejecutarlo sin el servicio](#ejecutarlo-sin-el-servicio)
18. [Mirar dentro de la base de datos](#mirar-dentro-de-la-base-de-datos)
19. [Solución de problemas](#solución-de-problemas)
20. [Desinstalación](#desinstalación)

---

## Qué hace

ainonyproxy es un proxy de privacidad para modelos de lenguaje (LLMs). Tus aplicaciones envían sus solicitudes de chat a ainonyproxy en lugar de enviarlas a OpenAI, Anthropic, DeepSeek, un Ollama local, etc. Para cada solicitud, ainonyproxy:

1. Detecta información personal (nombres, direcciones de correo electrónico, números de teléfono, IBAN, direcciones IP, lugares, números de documento...) con [Presidio](https://microsoft.github.io/presidio/) y spaCy, ejecutándose en tu propia computadora.
2. Reemplaza cada dato personal por un marcador como `<PERSON_1>` o `<EMAIL_ADDRESS_1>`.
3. Envía la conversación enmascarada al proveedor que elegiste.
4. Vuelve a poner los valores reales en la respuesta antes de devolvérsela a tu aplicación.

El proveedor nunca ve los datos personales, y tu aplicación no nota nada: habla la API de chat de OpenAI, con o sin streaming.

También tiene un panel web, con tema claro y tema oscuro, que muestra estadísticas y las últimas solicitudes y gestiona los usuarios (que pueden crearse su propia cuenta y recuperar la contraseña por su cuenta).

## Dónde corre

| | |
|---|---|
| Sistema operativo | Debian 13 (trixie) o posterior, o Alpine Linux con un paquete `python3` de versión 3.13 o posterior |
| Python | 3.13 o posterior (el instalador lo verifica) |
| Disco | Unos 3 GB (paquetes de Python y los modelos de idioma de spaCy) |
| Memoria | 2 GB o más (cada modelo de idioma de spaCy se carga en memoria) |
| Red | Acceso a los proveedores de LLM que uses, y a PyPI y GitHub durante la instalación |
| Puertos | `11080` (HTTP, sólo redirige) y `11443` (HTTPS) |

Está pensado para usarse desde la misma computadora en la que corre: tus aplicaciones hablan con `https://localhost:11443`.

## Instalación

Ejecutá el instalador como `root`. Hace todo solo y no pregunta nada.

**Debian** (una Debian mínima, como la imagen de Docker, no trae curl, así que la línea lo instala primero):

```bash
apt-get update && apt-get install -y curl ca-certificates && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --install
```

**Alpine Linux** (no trae bash por defecto, así que la línea lo instala primero):

```bash
apk add --no-cache bash curl && curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-alpine.sh | bash -s -- --install
```

También podés ejecutarlo desde una copia del repositorio: `bash deploy/install-update-reinstall-debian.sh --install`. En ese caso usa el código de esa copia en lugar de descargarlo.

Podés volver a ejecutarlo sin miedo: los instaladores son idempotentes, así que ejecutar uno dos veces con la misma opción deja el sistema igual que ejecutarlo una sola vez. Están hechos para descargarse con `curl` y pasarse directamente a `bash`: no se ejecuta nada hasta que llegó el script entero, así que una descarga cortada a la mitad no hace nada. Pasalos a `bash`, no a `sh`: con `sh` se frenan y te lo avisan.

### Qué hace el instalador

1. Instala los paquetes del sistema que necesita (Python, compilador, OpenSSL, curl...).
2. Verifica que Python sea 3.13 o posterior.
3. Crea el usuario de sistema `ainonyproxy` (sin contraseña, sin shell de login), cuyo home es `/opt/ainonyproxy/`.
4. Copia el código a `/opt/ainonyproxy/webapp/` y crea el entorno virtual de Python en `/opt/ainonyproxy/venv/`.
5. Copia la configuración por defecto a `/opt/ainonyproxy/config/` (sólo los archivos que todavía no existen: nunca pisa los tuyos).
6. Instala los modelos de spaCy de los idiomas configurados en `pii_detection.json`.
7. Crea un certificado autofirmado cuando no hay un certificado de Let's Encrypt.
8. Crea el administrador del panel `admin` con una contraseña aleatoria (sólo la primera vez).
9. Instala e inicia el servicio (`systemd` en Debian, `OpenRC` en Alpine) y espera hasta que responda.

La primera instalación tarda varios minutos: los paquetes de Python y los modelos de spaCy son grandes. En Alpine puede que haya que compilar algunos paquetes, lo que tarda más.

### Dónde está la contraseña

| Archivo | Contenido |
|---|---|
| `/root/webapp-credentials.txt` | El usuario y la contraseña del administrador del panel |
| `/root/webapp-install.log` | Todo lo que hizo el instalador, con la salida de cada comando |

Sólo root puede leer ambos (modo `600`).

### En contenedores

En un contenedor sin systemd (Docker), el instalador inicia ainonyproxy como un simple proceso en segundo plano y te avisa que no arrancará solo después de reiniciar el contenedor: ejecutá el instalador de nuevo para iniciarlo. En Alpine prepara OpenRC para que el servicio pueda correr dentro del contenedor.

## Actualización y reinstalación

| Comando | Qué hace |
|---|---|
| `--install` | Instala. En una instalación existente se comporta como `--update`. |
| `--update` | Reemplaza el código y actualiza las dependencias y los modelos. Conserva la configuración, la base de datos, los usuarios, los certificados y las contraseñas. |
| `--reinstall` | Elimina el código, el entorno virtual, la configuración, la base de datos y los registros (**no** los certificados) y vuelve a instalar desde cero, con una contraseña de administrador nueva. Pide confirmación; agregá `--yes` para saltear la pregunta. |

```bash
curl -fsSL https://raw.githubusercontent.com/nipegun/ainonyproxy/main/deploy/install-update-reinstall-debian.sh | bash -s -- --update
```

## Cómo abrirlo

| Qué | Dirección |
|---|---|
| Panel | `https://localhost:11443/` (te lleva al login) |
| Login | `https://localhost:11443/auth/login/` |
| Crear una cuenta | `https://localhost:11443/auth/register/` (cuando el registro está abierto) |
| Recuperar la contraseña | `https://localhost:11443/auth/recover/` |
| API de IA | `https://localhost:11443/api/ai/{provider}` |
| Documentación de la API (Swagger) | `https://localhost:11443/api/doc/` |
| Estado | `https://localhost:11443/api/ai/status` |

Todo lo que llega a `http://...:11080` se redirige de forma permanente a la misma dirección en `https://...:11443`.

Con el certificado autofirmado, el navegador muestra una advertencia la primera vez: es lo esperado, la conexión va cifrada de todos modos. Mirá [Certificados](#certificados) para usar uno real.

## Iniciar sesión

Abrí el panel e iniciá sesión con el usuario y la contraseña de `/root/webapp-credentials.txt`. Si abrís la dirección de un panel sin haber iniciado sesión, te envía al login y, después, de vuelta a la página que pediste.

Hay dos roles:

| Rol | Qué puede hacer |
|---|---|
| `admin` | Todo: ambos paneles, estadísticas, registros de solicitudes, gestión de usuarios |
| `user` | El panel de usuario: datos de conexión de la API, contraseña propia |

Una sesión dura 12 horas (`dashboard.session_hours`). Después de 5 intentos fallidos desde la misma dirección, el login queda bloqueado durante 15 minutos.

### Crear una cuenta

Cuando el registro está abierto, cualquiera que llegue al login puede crearse una cuenta en `/auth/register/` (enlace «Crear una cuenta» del login). Estas cuentas tienen siempre el rol `user`: solo un administrador puede hacer `admin` a alguien. El registro está abierto por defecto, y un administrador lo abre o lo cierra en **Usuarios → Registro**. Una misma dirección puede crear hasta 5 cuentas por hora.

Apenas creás la cuenta, la página muestra una sola vez su código de recuperación. Cuando confirmás que lo guardaste, «Ir a mi panel» abre el panel de usuario con la sesión ya iniciada.

### Códigos de recuperación

Cada cuenta puede tener un código de recuperación, como `ABCDE-FGHJK-LMNPQ-RSTUV`, para establecer una contraseña nueva sin un administrador. Se muestra una sola vez: ainonyproxy guarda solamente su huella (SHA-256), así que nadie puede volver a mostrarlo. Copialo o anotalo y guardalo en un lugar seguro.

| Cuándo | Quién ve el código |
|---|---|
| Te creás la cuenta en `/auth/register/` | Vos |
| Un administrador crea tu usuario en **Usuarios** | El administrador, que te lo pasa |
| Tocás **Generar un código de recuperación nuevo** en **Cuenta** (pide tu contraseña actual) | Vos. El código anterior deja de funcionar. |
| Lo usás en `/auth/recover/` | Recibís uno nuevo: cada código sirve una sola vez |

El administrador que crea el instalador y los usuarios creados desde la terminal arrancan sin código: generá uno en **Cuenta**.

### Si te olvidás la contraseña

Abrí `/auth/recover/` (enlace «¿Olvidaste tu contraseña?» del login) y escribí tu usuario, tu código de recuperación (con o sin guiones, en mayúsculas o minúsculas) y dos veces la contraseña nueva. La contraseña cambia, se cierran todas las sesiones de la cuenta y la página muestra tu código de recuperación nuevo. Los intentos erróneos cuentan como logins fallidos: después de 5 desde la misma dirección, hay que esperar 15 minutos.

Sin código de recuperación, un administrador te puede asignar una contraseña nueva en **Usuarios**, y root lo puede hacer desde la terminal del servidor (sección siguiente).

### Restablecer una contraseña desde la terminal

Si ya nadie puede iniciar sesión, establecé una contraseña nueva desde el servidor como root:

```bash
printf '%s\n' 'TheNewPassword' | AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/ainonyproxy.py --set-user admin --role admin --password-stdin
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/db
```

El mismo comando crea el usuario si no existe. `--list-users` lista los usuarios. Las contraseñas necesitan al menos 8 caracteres.

## El panel de administración

`/admin/dashboard/` abre la pestaña **Resumen**. Cada pestaña tiene su propia dirección, así que podés guardarla en marcadores o abrirla directamente.

| Pestaña | Dirección | Qué tiene |
|---|---|---|
| Resumen | `/admin/dashboard/overview/` | Solicitudes totales, solicitudes con PII enmascarada, tiempo promedio de escaneo, solicitudes de la última hora, los tipos de entidades de PII más detectados y las últimas 50 solicitudes. Se actualiza cada 5 segundos. Hacé clic en una solicitud para ver su contenido enmascarado (cuando se registra). |
| Usuarios | `/admin/dashboard/users/` | Abrir o cerrar el registro en `/auth/register/`. Crear usuarios (nombre, contraseña, rol): el código de recuperación del usuario nuevo se muestra una vez para que se lo pases. Asignarles una contraseña nueva, eliminarlos. No se puede eliminar al último administrador ni a tu propio usuario. |
| Cuenta | `/admin/dashboard/account/` | Tus datos, el formulario para cambiar tu contraseña (al cambiarla se cierran tus otras sesiones) y el de generar un código de recuperación nuevo. |
| Ayuda | `/admin/dashboard/help/` | Un resumen de cómo usar ainonyproxy. |

La barra lateral también tiene un enlace al panel de usuario, el botón para cerrar sesión, el selector de tema (mirá [Tema claro y tema oscuro](#tema-claro-y-tema-oscuro)) y el selector de idioma (en-GB, en-US, es-AR, es-ES, fr-FR). Todas las horas se muestran en UTC con el formato `2026/10/29@13:59:59.723`.

## El panel de usuario

`/user/dashboard/` abre la pestaña **API**.

| Pestaña | Dirección | Qué tiene |
|---|---|---|
| API | `/user/dashboard/api/` | La URL base, un ejemplo con `curl` y la tabla de proveedores disponibles con su endpoint. |
| Cuenta | `/user/dashboard/account/` | Tus datos, el formulario para cambiar tu contraseña y el de generar un código de recuperación nuevo. |
| Ayuda | `/user/dashboard/help/` | Un resumen de cómo usar ainonyproxy. |

## Tema claro y tema oscuro

Todas las páginas (login, registro, recuperación de la contraseña y los dos paneles) tienen un tema claro y uno oscuro. El selector de tema está al pie de la barra lateral de los paneles y debajo de la tarjeta de las páginas de login. Tiene tres botones:

| Botón | Tema |
|---|---|
| Sistema (ícono de pantalla) | El tema de tu sistema operativo. Es el predeterminado, y la página cambia sola cuando cambia el del sistema. |
| Claro (ícono de sol) | Siempre claro. |
| Oscuro (ícono de luna) | Siempre oscuro. |

La elección se recuerda en este navegador (`localStorage`, clave `ainonyproxy_theme`) y se aplica a todas las páginas de ainonyproxy abiertas en él.

## Enviar solicitudes a través de ainonyproxy

Apuntá tu aplicación a `https://localhost:11443/api/ai/{provider}` en lugar de a la URL del proveedor, y enviá la misma solicitud de chat al estilo OpenAI:

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

El proveedor recibe `Write an e-mail to <PERSON_1>, his address is <EMAIL_ADDRESS_1>` y tu aplicación recibe la respuesta con el nombre y la dirección reales de vuelta en su lugar.

- `-k` le indica a curl que acepte el certificado autofirmado. Otros clientes tienen una opción similar, o podés instalar el certificado como de confianza.
- Agregá `"stream": true` para streaming (Server-Sent Events, como OpenAI).
- `messages` acepta los roles `system`, `user` y `assistant`, con contenido de texto.
- Los demás campos (`temperature`, `max_tokens`, `stop`...) se pasan al proveedor. Para Anthropic se convierten a su formato.
- `GET /api/ai/` lista los proveedores con su URL completa.

### Encabezados de respuesta

| Encabezado | Significado |
|---|---|
| `X-Ainonyproxy-Provider` | Proveedor usado |
| `X-Ainonyproxy-PII-Detected` | `true` cuando el último mensaje del usuario tenía PII |
| `X-Ainonyproxy-PII-Masked` | `true` cuando la conversación se enmascaró |
| `X-Ainonyproxy-Language` | Idioma usado para la detección |
| `X-Ainonyproxy-Language-Fallback` | `true` cuando el idioma detectado no estaba configurado y se usó el de respaldo |
| `X-Request-ID` | Identificador de la solicitud (el tuyo, si enviaste uno) |

### Errores

| Código | Cuándo |
|---|---|
| `400` | El cuerpo no es una solicitud de chat válida |
| `404` | El proveedor no existe |
| `502` | El proveedor respondió con un error, o no se pudo contactar |
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

Cada entrada también puede tener `"format"` (`openai` o `anthropic`; se deduce de la URL cuando falta) y `"model"` (un modelo que se usa siempre, sin importar lo que pida el cliente). El nombre de la entrada es el nombre en la URL: `/api/ai/openai`.

Las claves están en `/opt/ainonyproxy/config/api_keys.json`, aparte del resto para que sólo este archivo tenga los secretos:

```json
{
  "openai": "sk-...",
  "anthropic": "sk-ant-...",
  "ollama": ""
}
```

Los proveedores locales (`localhost`, `10.x`, `172.16-31.x`, `192.168.x`) pueden tener la clave vacía. Los valores pueden usar variables de entorno: `"${OPENAI_API_KEY}"`.

Después de editar cualquiera de los dos archivos, conservá el propietario y reiniciá:

```bash
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/config/*.json
chmod 600 /opt/ainonyproxy/config/*.json
systemctl restart ainonyproxy        # Debian
rc-service ainonyproxy restart       # Alpine
```

Incluidos por defecto: `anthropic`, `deepseek`, `gemini`, `kimi`, `llamacpp`, `ollama`, `openai`, `openrouter`, `vllm` y `zai`. `gemini` está declarado pero se envía como compatible con OpenAI, lo que la API nativa de Gemini no entiende; y `llamacpp` apunta a `/completion`, que no es un endpoint de chat. Usá la URL compatible con OpenAI de esos servidores si los necesitás.

## Detección de PII

Se configura en `/opt/ainonyproxy/config/pii_detection.json`:

| Clave | Significado | Valor por defecto |
|---|---|---|
| `languages` | Idiomas a detectar (códigos de spaCy: `en`, `es`, `fr`, `de`, `it`, `pt`, `ca`...) | `["es", "en"]` |
| `fallback_language` | Idioma que se usa cuando el detectado no está en la lista | `es` |
| `score_threshold` | Confianza mínima (de 0 a 1) para tratar algo como PII. Más bajo encuentra más, pero también más falsos positivos. | `0.5` |
| `entities` | Tipos de entidades de Presidio a buscar | Una lista amplia (`PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `IBAN_CODE`, `ES_NIF`...) |

Cada idioma necesita su modelo de spaCy. Después de agregar uno, instalá su modelo y reiniciá:

```bash
/opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/presidio/setup.py --languages fr
chown -R ainonyproxy:ainonyproxy /opt/ainonyproxy/venv
systemctl restart ainonyproxy
```

O ejecutá el instalador con `--update`, que instala los modelos de todos los idiomas configurados. ainonyproxy se niega a arrancar cuando un idioma configurado no tiene modelo, para que nunca deje pasar datos personales por error.

Sólo el último mensaje del usuario decide si una conversación tiene PII. Cuando la tiene, se enmascaran todos los mensajes del usuario y del asistente, y el mismo valor siempre recibe el mismo marcador.

## Qué se escribe en la base de datos

Cada solicitud se registra en `/opt/ainonyproxy/db/ainonyproxy.db`: hora, proveedor, modelo, si tenía PII, tipos de entidades, idioma, tiempos y tokens. Que los textos también se registren depende de `config.json`:

| Clave | Qué controla | Valor por defecto |
|---|---|---|
| `logging.log_content` | Solicitud original y respuesta al cliente (con los datos personales reales) | `false` |
| `logging.log_masked_content` | Solicitud enmascarada y respuesta del proveedor (con marcadores) | `true` |
| `logging.retention_days` | Días que se conserva una solicitud; `0` las conserva para siempre | `30` |

Con los valores por defecto, la base de datos nunca guarda los datos personales en sí.

La misma base de datos guarda los usuarios del panel (solo las huellas de sus contraseñas y de sus códigos de recuperación, nunca los valores), sus sesiones (solo la huella de cada token) y los ajustes que un administrador cambia desde el panel (tabla `app_settings`, como si el registro está abierto).

## Referencia de configuración

`/opt/ainonyproxy/config/config.json`:

| Clave | Significado | Valor por defecto |
|---|---|---|
| `mode` | Sólo existe `mask` | `mask` |
| `server.host` | Dirección en la que escuchar | `0.0.0.0` |
| `server.port` | Puerto HTTP (sólo redirige a HTTPS) | `11080` |
| `server.ssl_port` | Puerto HTTPS | `11443` |
| `server.proxy_protocol` | Esperar el protocolo PROXY en HTTPS (para un HAProxy por delante con `send-proxy`) | `false` |
| `server.ssl.enabled` / `certfile` / `keyfile` | Certificado propio, que se usa cuando no hay un certificado de Let's Encrypt en la carpeta de certificados | `false` |
| `masking.show_markers` | Poner `marker_text` delante de cada valor desenmascarado en las respuestas | `false` |
| `masking.marker_text` | Texto que usa `show_markers` | `[protected]` |
| `logging.*` | Mirá [Qué se escribe en la base de datos](#qué-se-escribe-en-la-base-de-datos) | |
| `logging.database` | Ruta de la base de datos SQLite | `/opt/ainonyproxy/db/ainonyproxy.db` |
| `dashboard.enabled` | Reservado; el panel siempre está disponible | `true` |
| `dashboard.session_hours` | Duración de una sesión del panel | `12` |
| `ui.default_language` | Idioma de la interfaz para quien no eligió uno | `en-US` |

Reiniciá el servicio después de modificarla.

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

Todo pertenece al usuario `ainonyproxy`. `config/`, `db/` y `certificates/` sólo puede leerlas él (y root).

## Certificados

Si no hay nada más, ainonyproxy sirve HTTPS con un certificado autofirmado (`/opt/ainonyproxy/certificates/selfsigned-fullchain.pem`), válido para `localhost`, `127.0.0.1` y el nombre de la máquina.

Para usar un certificado de Let's Encrypt, copiá sus dos archivos a la carpeta de certificados con estos nombres y reiniciá:

```bash
cp /etc/letsencrypt/live/your.domain/fullchain.pem /opt/ainonyproxy/certificates/fullchain.pem
cp /etc/letsencrypt/live/your.domain/privkey.pem /opt/ainonyproxy/certificates/privkey.pem
chown ainonyproxy:ainonyproxy /opt/ainonyproxy/certificates/*.pem
chmod 600 /opt/ainonyproxy/certificates/privkey.pem
systemctl restart ainonyproxy
```

Tienen prioridad sobre todo lo demás. Repetí la copia después de cada renovación.

## Ejecutarlo sin el servicio

`deploy/run.sh` (en una copia del repositorio) crea el entorno virtual, instala lo que falta e inicia ainonyproxy en primer plano, mostrando todo lo que hace. Detenelo con `Ctrl+C`.

```bash
bash deploy/run.sh                                   # as root, uses /opt/ainonyproxy
AINONYPROXY_HOME="$PWD/_/temp/home" bash deploy/run.sh   # as any user, in a folder of your own
```

Si el servicio instalado está corriendo, detenelo primero: ambos usan los mismos puertos (ainonyproxy detiene lo que siga escuchando en ellos antes de arrancar).

Cuando todavía no hay usuarios (nunca se instaló), el primer arranque crea `admin` e imprime su contraseña una sola vez en la terminal.

## Mirar dentro de la base de datos

```bash
AINONYPROXY_HOME=/opt/ainonyproxy /opt/ainonyproxy/venv/bin/python3 /opt/ainonyproxy/webapp/backend/view_database.py
```

Un menú muestra los usuarios, las sesiones, las últimas solicitudes, el detalle de una solicitud, los contenidos enmascarados y estadísticas generales.

## Solución de problemas

| Qué pasa | Qué hacer |
|---|---|
| El servicio no arranca | `journalctl -u ainonyproxy -n 100 --no-pager` (Debian) o `/opt/ainonyproxy/logs/ainonyproxy.log` (Alpine y contenedores). |
| "Missing spaCy models" | Instalá los modelos de los idiomas configurados (mirá [Detección de PII](#detección-de-pii)) o ejecutá el instalador con `--update`. |
| Un proveedor responde 502 | Revisá su URL en `api_urls.json` y su clave en `api_keys.json`. El detalle del error está en la respuesta. |
| "Remote providers without an API key" al arrancar | Agregá sus claves a `api_keys.json`, o ignoralo para los proveedores que no uses. |
| El navegador advierte sobre el certificado | Es lo esperado con el certificado autofirmado. Mirá [Certificados](#certificados). |
| "Demasiados intentos fallidos" | Esperá 15 minutos, o reiniciá el servicio. |
| Nadie recuerda la contraseña del administrador | Mirá [Restablecer una contraseña desde la terminal](#restablecer-una-contraseña-desde-la-terminal). |
| «El registro está cerrado» | Un administrador lo abre en **Usuarios → Registro**, o te crea la cuenta. |
| Perdiste el código de recuperación | Mientras puedas iniciar sesión, generá uno nuevo en **Cuenta → Código de recuperación**. Si no podés iniciar sesión, un administrador te asigna una contraseña nueva en **Usuarios**. |
| El primer arranque tarda mucho | Cargar los modelos de spaCy lleva desde varios segundos hasta un minuto; el instalador espera hasta 3 minutos. |

## Desinstalación

Como root:

```bash
systemctl disable --now ainonyproxy && rm -f /etc/systemd/system/ainonyproxy.service && systemctl daemon-reload   # Debian
rc-service ainonyproxy stop; rc-update del ainonyproxy default; rm -f /etc/init.d/ainonyproxy                     # Alpine
rm -rf /opt/ainonyproxy
userdel ainonyproxy     # Debian (on Alpine: deluser ainonyproxy)
rm -f /root/webapp-credentials.txt /root/webapp-install.log
```
