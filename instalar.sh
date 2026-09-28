#!/usr/bin/env bash
# Instala o actualiza leygo con Docker en tu computador.
#
#   ./instalar.sh                      solo leygo (usa tu Redis, Qdrant y Ollama)
#   ./instalar.sh --redis --qdrant     además levanta Redis y Qdrant dentro de Docker
#   ./instalar.sh --todo               Redis + Qdrant + Ollama en Docker
#
# Opciones:
#   --redis        Redis en Docker (sesiones y conversaciones)
#   --qdrant       Qdrant en Docker (memoria vectorial)
#   --ollama       Ollama en Docker (modelos y embeddings locales)
#   --todo         los tres
#   --ninguno      ninguno en Docker (usa los tuyos o servicios en la nube)
#   --dominio X    dominio para Caddy (por defecto :80, http://localhost sin TLS)
#   --version X    versión de leygo a instalar (por defecto la última; queda en .env)
#   --sin-build    no reconstruye ni descarga las imágenes
#
# Con el código fuente (hay Dockerfile) arma las imágenes; en la instalación descargada de
# leygo.cl baja las ya compiladas (docker compose pull). Correrlo de nuevo actualiza.
#
# La selección queda en .env (COMPOSE_PROFILES): `./instalar.sh` sin opciones (o `docker compose up -d`)
# vuelve a levantar lo mismo. Para cambiarla, córrelo con otras opciones.
set -euo pipefail
cd "$(dirname "$0")"

redis=0; qdrant=0; ollama=0; dominio=""; build=1; eligio=0; version=""
while [ $# -gt 0 ]; do
  case "$1" in
    --redis) redis=1; eligio=1 ;;
    --qdrant) qdrant=1; eligio=1 ;;
    --ollama) ollama=1; eligio=1 ;;
    --todo|--local) redis=1; qdrant=1; ollama=1; eligio=1 ;;
    --ninguno) eligio=1 ;;
    --dominio) shift; dominio="${1:-}" ;;
    --dominio=*) dominio="${1#*=}" ;;
    --sin-build) build=0 ;;
    --version) shift; version="${1:-}" ;;
    --version=*) version="${1#*=}" ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Opción desconocida: $1 (usa --help)"; exit 1 ;;
  esac
  shift
done

command -v docker >/dev/null || { echo "Falta Docker: instala Docker Desktop (https://docs.docker.com/get-docker/)"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Falta 'docker compose' (viene con Docker Desktop o el plugin compose)"; exit 1; }

[ -f .env ] || { cp .env.example .env; chmod 600 .env; echo "✓ .env creado desde .env.example"; }
mkdir -p data config

# Lee y escribe variables de .env sin depender de sed -i (distinto en macOS y Linux).
leer() { grep -E "^$1=" .env | tail -n1 | cut -d= -f2- | sed -e 's/[[:space:]]*#.*$//' -e "s/^['\"]//" -e "s/['\"]$//" || true; }
poner() {
  local k="$1" v="$2" tmp
  tmp="$(mktemp)"
  if grep -qE "^$k=" .env; then
    awk -v k="$k" -v v="$v" 'BEGIN{FS=OFS="="} $1==k && !hecho {print k "=" v; hecho=1; next} {print}' .env > "$tmp"
  else
    cat .env > "$tmp"; printf '%s=%s\n' "$k" "$v" >> "$tmp"
  fi
  cat "$tmp" > .env; rm -f "$tmp"
}
# Dentro de Docker "localhost" es el propio contenedor: tu computador es host.docker.internal.
local_a_host() { printf '%s' "$1" | sed -E 's#(localhost|127\.0\.0\.1)#host.docker.internal#'; }
es_local() { printf '%s' "$1" | grep -qE '(^|//)(localhost|127\.0\.0\.1)(:|/|$)'; }
# Apunta al servicio de Docker de leygo (que se apaga si no se elige).
es_docker() { printf '%s' "$1" | grep -qE "^(https?://)?$2(:|/|$)"; }

# Sin opciones de servicios: se repite la selección anterior.
if [ $eligio = 0 ] && grep -qE '^COMPOSE_PROFILES=' .env; then
  prev=",$(leer COMPOSE_PROFILES),"
  case "$prev" in *,redis,*|*,local,*) redis=1 ;; esac
  case "$prev" in *,qdrant,*|*,local,*) qdrant=1 ;; esac
  case "$prev" in *,ollama,*|*,local,*) ollama=1 ;; esac
  echo "Misma selección que la vez anterior ($(leer COMPOSE_PROFILES | sed 's/^$/ninguno en Docker/')). Cámbiala con --redis, --qdrant, --ollama, --todo o --ninguno."
fi

perfiles=""
agregar() { perfiles="${perfiles:+$perfiles,}$1"; }
echo
echo "Servicios:"

if [ $redis = 1 ]; then
  agregar redis
  h="$(leer REDIS_HOST)"
  if [ -z "$h" ] || es_local "$h"; then poner REDIS_HOST redis; poner REDIS_PORT 6379; fi
  echo "  • Redis   → en Docker (redis:6379)"
else
  h="$(leer REDIS_HOST)"
  if es_docker "$h" redis; then echo "  ! Redis de Docker queda apagado (sus datos siguen en el volumen). Apunto a tu computador."; fi
  if [ -z "$h" ] || es_local "$h" || es_docker "$h" redis; then poner REDIS_HOST host.docker.internal; h=host.docker.internal; fi
  echo "  • Redis   → el tuyo ($h:$(leer REDIS_PORT))"
fi

if [ $qdrant = 1 ]; then
  agregar qdrant
  u="$(leer QDRANT_URL)"
  if [ -z "$u" ] || es_local "$u"; then poner QDRANT_URL http://qdrant:6333; fi
  echo "  • Qdrant  → en Docker (http://qdrant:6333)"
else
  u="$(leer QDRANT_URL)"; [ -n "$u" ] || u="http://localhost:6333"
  if es_docker "$u" qdrant; then echo "  ! Qdrant de Docker queda apagado (sus datos siguen en el volumen). Apunto a tu computador."; u="http://host.docker.internal:6333"; poner QDRANT_URL "$u"; fi
  if es_local "$u"; then u="$(local_a_host "$u")"; poner QDRANT_URL "$u"; fi
  echo "  • Qdrant  → el tuyo ($u)"
fi

if [ $ollama = 1 ]; then
  agregar ollama
  u="$(leer OLLAMA_BASE_URL)"
  if [ -z "$u" ] || es_local "$u"; then poner OLLAMA_BASE_URL http://ollama:11434; fi
  echo "  • Ollama  → en Docker (http://ollama:11434)"
else
  u="$(leer OLLAMA_BASE_URL)"; [ -n "$u" ] || u="http://localhost:11434"
  if es_docker "$u" ollama; then u="http://host.docker.internal:11434"; poner OLLAMA_BASE_URL "$u"; fi
  if es_local "$u"; then u="$(local_a_host "$u")"; poner OLLAMA_BASE_URL "$u"; fi
  echo "  • Ollama  → el tuyo o un proveedor de pago para embeddings ($u)"
fi

poner COMPOSE_PROFILES "$perfiles"

# Lo que guardó el asistente (data/env.gui) tiene prioridad sobre .env.
if grep -qE '^(REDIS_HOST|QDRANT_URL|OLLAMA_BASE_URL)=' data/env.gui 2>/dev/null; then
  echo "  ! El asistente ya guardó conexiones en data/env.gui y esas mandan. Si cambiaste de servicios, ajústalas en Ajustes → Asistente de configuración."
fi

if [ -n "$dominio" ]; then poner DOMAIN "$dominio"
elif [ -z "$(leer DOMAIN)" ]; then poner DOMAIN ":80"
fi
echo "  • Dominio → $(leer DOMAIN)"

if [ -n "$version" ]; then poner LEYGO_VERSION "${version#v}"; fi
echo "  • Versión → $(leer LEYGO_VERSION | sed 's/^$/la última/')"
echo

if [ $build = 0 ]; then docker compose up -d --remove-orphans
elif [ -f Dockerfile ]; then docker compose up -d --build --remove-orphans
else
  echo "Descargando leygo…"
  docker compose pull --quiet
  docker compose up -d --remove-orphans
fi

d="$(leer DOMAIN)"
case "$d" in
  :80|"") url="http://localhost" ;;
  :*) url="http://localhost${d}" ;;
  *) url="https://$d" ;;
esac

echo
echo "Listo. Abre $url"
echo "La primera vez te pide un código de un solo uso. Lo ves con:"
echo "  docker compose logs agent | grep -A4 'configuración'"
echo
echo "Puedes cambiar Redis, Qdrant y los embeddings después en el asistente (Ajustes)."
