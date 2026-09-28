# leygo

Tu agente personal, en tu servidor o en tu computador: lee tu correo, tu calendario y tus reuniones, lleva la cuenta de lo que prometiste y de lo que te deben, y te pregunta antes de hacer algo importante.

Sitio: **https://leygo.cl**

Este repositorio trae **solo lo necesario para instalar leygo**: la configuración de Docker y el instalador. leygo se distribuye compilado, en imágenes de contenedor (`ghcr.io/jesusmaster/leygo-agent` y `leygo-gui`), y es gratis bajo la [licencia de uso](LICENCIA.txt).

## Instalar

Necesitas Docker (Docker Desktop en Mac o Windows, o Docker Engine con el plugin compose en Linux).

**En tu computador**, con Redis y Qdrant dentro de Docker:

```bash
curl -fsSL https://leygo.cl/instalar.sh | bash -s -- --redis --qdrant
```

Queda en la carpeta `leygo` y la interfaz en http://localhost.

**En un servidor**, con tu dominio apuntando a él (Caddy saca el certificado solo):

```bash
curl -fsSL https://leygo.cl/instalar.sh | bash -s -- --dominio agente.tudominio.cl --redis --qdrant
```

Después abre la dirección que muestra el instalador. La primera vez te pide un código de un solo uso:

```bash
cd leygo && docker compose logs agent | grep -A4 'configuración'   # si no lo mostró el instalador
```

y el asistente te guía por tu cuenta, la personalidad del agente, el modelo, los embeddings, Redis y Qdrant, Google y Telegram.

### Opciones del instalador

| Opción | Qué hace |
| --- | --- |
| `--redis` `--qdrant` `--ollama` | Levanta esos servicios dentro de Docker. Los que no elijas, leygo los busca en tu computador o en la nube. |
| `--todo` / `--ninguno` | Los tres / ninguno. |
| `--dominio X` | Dominio con TLS automático (sin esto: `http://localhost`). |
| `--puerto 8080` | Puerto de la interfaz en tu computador (sin esto: 80). |
| `--version 1.4.0` | Fija una versión. Sin esto, la última. |

La selección queda en `.env`: correr `./instalar.sh` sin opciones repite lo mismo.

### Varios leygo en el mismo computador

Cada uno en su carpeta y con su puerto. `--carpeta` elige la carpeta (por defecto `leygo`):

```bash
curl -fsSL https://leygo.cl/instalar.sh | bash -s -- --carpeta leygo-pruebas --puerto 8080 --redis --qdrant
```

Cada carpeta es un proyecto de Docker aparte, con sus propios datos, su Redis y su Qdrant. Si el puerto está ocupado, el instalador te avisa.

## Actualizar

```bash
cd leygo && ./instalar.sh
```

Baja las imágenes nuevas y reinicia. Tus datos (`data/`), tu `.env` y tu `config/` no se tocan.

## Tus datos

Todo queda en la carpeta `leygo`: `data/` (base SQLite, agentes personalizados, adjuntos), `config/` y `.env`, más los volúmenes de Docker de Redis y Qdrant. Para respaldar, copia esa carpeta.

## Problemas y sugerencias

Abre un *issue* en este repositorio.

## Licencia

leygo es gratis para usar en tus equipos, personal o dentro de tu organización. No se puede redistribuir, vender ni ofrecer como servicio a terceros. Detalle en [LICENCIA.txt](LICENCIA.txt). Los componentes de terceros que incluye mantienen sus propias licencias (`/app/AVISOS_DE_TERCEROS.txt` en la imagen).
