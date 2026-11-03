# ainonyproxy

Este README también está disponible en:\
[en-GB](README.en-GB.md), [en-US](../README.md), es-AR, [es-ES](README.es-ES.md), [fr-FR](README.fr-FR.md)

## Qué es

Un proxy de privacidad para modelos de chat de IA (LLMs) que se ejecuta en tu propia computadora GNU/Linux (Debian o Alpine).

Tus aplicaciones envían sus solicitudes de chat a ainonyproxy en lugar de enviarlas al proveedor de IA, y ainonyproxy:

- Encuentra los datos personales en los mensajes (nombres, correos electrónicos, teléfonos, IBAN, direcciones, números de documento...).
- Los reemplaza por marcadores como `<PERSON_1>` antes de que algo salga de tu computadora.
- Envía la conversación enmascarada a OpenAI, Anthropic, DeepSeek, Ollama, OpenRouter, vLLM, etc.
- Vuelve a poner los datos reales en la respuesta.

Habla la API de chat de OpenAI (con streaming) y tiene un panel web con estadísticas, registros de solicitudes y usuarios.

## Capturas de pantalla

![Panel de ainonyproxy](https://raw.githubusercontent.com/nipegun/ainonyproxy/main/doc/screenshot.png)

## Instalación

Ejecutalo como `root`.

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

Después abrí `https://localhost:11443/` e iniciá sesión con la contraseña guardada en `/root/webapp-credentials.txt`.

## Leé la documentación

Explorá:

- [doc/MANUAL.es-AR.md](MANUAL.es-AR.md) para aprender a instalarlo, configurarlo y usarlo.
- [doc/CODE.es-AR.md](CODE.es-AR.md) para entender cómo está construido (para desarrolladores y para modelos de IA).

## Patrociná este proyecto

- **[Contratame](mailto:nipegun@gmail.com?subject=I%20want%20to%20hire%20you%21)** para agregar nuevas funcionalidades.
- **GitHub Sponsors.** También podés apoyar el proyecto económicamente en GitHub: [github.com/sponsors/nipegun](https://github.com/sponsors/nipegun).
