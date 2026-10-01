#!/bin/sh
# Servicio "actualizador" de leygo (contenedor docker:cli con acceso a Docker).
#
# Es lo que ejecuta el botón "Actualizar" de la interfaz. El agente no tiene acceso a Docker: deja
# data/actualizacion/pedido.json con la versión y este servicio, cada pocos segundos:
#   1. valida la versión (solo números: 1.2.3),
#   2. si .env fija LEYGO_VERSION, la cambia a la nueva; si no, usa "latest" (que es la nueva: solo se
#      puede pedir la última publicada) y así un `docker compose up -d` posterior no vuelve atrás,
#   3. baja las imágenes de agent y gui y reinicia solo esos dos servicios.
# No ejecuta nada que venga del pedido además de ese número de versión.
#
# En un servidor que compila desde el código (hay Dockerfile; lo activa deploy.sh con el perfil
# actualizador-codigo) hace lo mismo que deploy.sh: git pull, build de agent y gui y los reinicia.
# Para el pull usa una copia de las llaves SSH del servidor (montadas de solo lectura).
#
# Anota su latido (actualizador.json) y el avance (estado.json) en la misma carpeta.
# Corre dentro de la carpeta de la instalación, montada en la misma ruta que en tu computador
# (LEYGO_DIR), para que docker compose encuentre ./data, ./config y el .env como siempre.
set -u

DIR="${LEYGO_DIR:-}"
[ -n "$DIR" ] && [ -f "$DIR/docker-compose.yml" ] || { echo "actualizador: LEYGO_DIR no apunta a la instalación ($DIR). Corre ./instalar.sh de nuevo."; sleep 3600; exit 1; }
cd "$DIR" || exit 1

A=data/actualizacion
mkdir -p "$A" && chmod 1777 "$A" 2>/dev/null
LOG="$A/ultima.log"
modo=imagenes; [ -f Dockerfile ] && modo=codigo
INTERVALO="${ACTUALIZADOR_INTERVALO:-5}"

# JSON mínimo sin jq: los textos se limpian de comillas, barras y saltos de línea.
limpio() { printf '%s' "$1" | tr '\n\r\t' '   ' | sed -e 's/\\/\//g' -e 's/"/'"'"'/g' | cut -c1-600; }
escribir() { # archivo contenido (atómico)
  printf '%s\n' "$2" > "$A/.$1.tmp" && mv -f "$A/.$1.tmp" "$A/$1"
}
estado() { # id estado version [error]
  e=""; [ -n "${4:-}" ] && e=",\"error\":\"$(limpio "$4")\""
  hasta=""; case "$2" in listo|error) hasta=",\"hasta\":$(date +%s)000" ;; esac
  escribir estado.json "{\"id\":\"$1\",\"estado\":\"$2\",\"version\":\"$3\",\"desde\":${desde}000${hasta}${e}}"
}
leer() { sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$2" | head -n1; }
fijada() { grep -qE '^LEYGO_VERSION=[^[:space:]#]' .env 2>/dev/null; }
fijar_version() {
  awk -v v="$1" 'BEGIN{FS=OFS="="} $1=="LEYGO_VERSION" && !h {print "LEYGO_VERSION=" v; h=1; next} {print}' .env > "$A/.env.tmp" && cat "$A/.env.tmp" > .env && rm -f "$A/.env.tmp"
}

if [ "$modo" = codigo ]; then
  command -v git >/dev/null 2>&1 || apk add --no-cache git openssh-client >/dev/null 2>&1 || echo "actualizador: no se pudo instalar git"
  if [ -d /root/.ssh-host ]; then
    mkdir -p /root/.ssh && cp -R /root/.ssh-host/. /root/.ssh/ 2>/dev/null
    chmod 700 /root/.ssh; chmod 600 /root/.ssh/* 2>/dev/null; chmod 644 /root/.ssh/*.pub /root/.ssh/known_hosts 2>/dev/null
  fi
  git config --global --add safe.directory "$DIR" 2>/dev/null
fi

# Servidor con el código: igual que deploy.sh (git pull, build y reinicio de agent y gui).
# Si sobre el código se corrió el instalador de leygo.cl, docker-compose.yml, instalar.sh y otros
# quedaron con la versión descargada (sin build:) y git pull no puede avanzar: se vuelve a los del código.
restaurar_descargados() {
  [ -f Dockerfile ] || return 0
  git diff --quiet -- docker-compose.yml 2>/dev/null && return 0
  grep -qE '^[[:space:]]+build:' docker-compose.yml && return 0
  local f l=""
  for f in docker-compose.yml instalar.sh instalar.ps1 deploy/actualizador.sh deploy/Caddyfile .env.example README.md LICENCIA.txt; do
    git ls-files --error-unmatch "$f" >/dev/null 2>&1 && ! git diff --quiet -- "$f" && l="$l $f"
  done
  [ -n "$l" ] || return 0
  echo "Estos archivos eran los de la instalación descargada (leygo.cl/instalar.sh), no los del código:$l"
  echo "Vuelvo a los del código (tu .env, config/ y data/ no se tocan)."
  # shellcheck disable=SC2086
  git checkout -- $l
}
actualizar_codigo() { # id version
  estado "$1" descargando "$2"
  restaurar_descargados >> "$LOG" 2>&1
  if ! git pull --ff-only > "$LOG" 2>&1; then estado "$1" error "$2" "git pull falló: $(tail -n 3 "$LOG")"; return; fi
  git fetch --tags -q >> "$LOG" 2>&1 || true
  VERSION_APP="$(git describe --tags --always 2>/dev/null || echo dev)"; export VERSION_APP
  if ! docker compose build agent >> "$LOG" 2>&1 || ! docker compose build gui >> "$LOG" 2>&1; then
    estado "$1" error "$2" "No se pudo compilar: $(tail -n 3 "$LOG")"; return
  fi
  estado "$1" reiniciando "$2"
  if docker compose up -d --no-deps agent gui >> "$LOG" 2>&1; then estado "$1" listo "$2"; echo "actualizador: listo, $VERSION_APP"
  else estado "$1" error "$2" "No se pudo reiniciar: $(tail -n 3 "$LOG")"; fi
}

echo "actualizador: vigilando $DIR/$A (modo $modo)"
while :; do
  escribir actualizador.json "{\"ts\":$(date +%s),\"modo\":\"$modo\"}"
  if [ -f "$A/pedido.json" ]; then
    id="$(leer id "$A/pedido.json")"; v="$(leer version "$A/pedido.json")"
    rm -f "$A/pedido.json"
    desde=$(date +%s)
    id="$(printf '%s' "$id" | tr -cd 'a-f0-9' | cut -c1-24)"
    if ! printf '%s' "$v" | grep -qE '^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,6}$'; then
      estado "$id" error "$(limpio "$v")" "Versión inválida"
    elif [ "$modo" = codigo ]; then
      echo "actualizador: actualizando desde el código (pedido $id)"
      actualizar_codigo "$id" "$v"
    else
      echo "actualizador: actualizando a $v (pedido $id)"
      estado "$id" descargando "$v"
      if fijada; then fijar_version "$v"; fi
      if ! docker compose pull --quiet agent gui > "$LOG" 2>&1; then
        estado "$id" error "$v" "No se pudieron descargar las imágenes de la versión $v: $(tail -n 3 "$LOG")"
      else
        estado "$id" reiniciando "$v"
        if docker compose up -d --no-deps agent gui >> "$LOG" 2>&1; then
          estado "$id" listo "$v"
          echo "actualizador: listo, leygo $v"
        else
          estado "$id" error "$v" "No se pudo reiniciar: $(tail -n 3 "$LOG")"
        fi
      fi
    fi
  fi
  sleep "$INTERVALO"
done
