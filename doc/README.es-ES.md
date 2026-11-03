# ainonyproxy

Este README también está disponible en:\
[en-GB](README.en-GB.md), [en-US](../README.md), [es-AR](README.es-AR.md), es-ES, [fr-FR](README.fr-FR.md)

## Qué es

Un proxy de privacidad para modelos de chat de IA (LLM) que se ejecuta en tu propio ordenador GNU/Linux (Debian o Alpine).

Tus aplicaciones envían sus peticiones de chat a ainonyproxy en lugar de enviárselas al proveedor de IA, y ainonyproxy:

- Encuentra los datos personales de los mensajes (nombres, correos electrónicos, teléfonos, IBAN, direcciones, números de identificación...).
- Los sustituye por marcadores como `<PERSON_1>` antes de que nada salga de tu ordenador.
- Envía la conversación enmascarada a OpenAI, Anthropic, DeepSeek, Ollama, OpenRouter, vLLM, etc.
- Vuelve a poner los datos reales en la respuesta.

Habla la API de chat de OpenAI (con streaming) y tiene un panel web con estadísticas, registros de peticiones y usuarios.

## Capturas de pantalla

![Panel de ainonyproxy](https://raw.githubusercontent.com/nipegun/ainonyproxy/main/doc/screenshot.png)

## Instalación

Ejecútalo como `root`.

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

Después abre `https://localhost:11443/` e inicia sesión con la contraseña guardada en `/root/webapp-credentials.txt`.

## Lee la documentación

Explora:

- [doc/MANUAL.es-ES.md](MANUAL.es-ES.md) para aprender a instalarlo, configurarlo y usarlo.
- [doc/CODE.es-ES.md](CODE.es-ES.md) para entender cómo está construido (para desarrolladores y para modelos de IA).

## Patrocina este proyecto

- **[Contrátame](mailto:nipegun@gmail.com?subject=I%20want%20to%20hire%20you%21)** para añadir nuevas funcionalidades.
- **GitHub Sponsors.** También puedes apoyar el proyecto económicamente en GitHub: [github.com/sponsors/nipegun](https://github.com/sponsors/nipegun).
