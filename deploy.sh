#!/bin/bash
# =============================================================================
# deploy.sh — Script de actualización segura para producción
# Uso: bash deploy.sh [--no-build]
# =============================================================================

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP_DIR="/tmp/leygo_deploy_backup_$(date +%Y%m%d_%H%M%S)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()   { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

backup_path() {
    local path="$1"
    local full="$REPO_DIR/$path"
    if [ -e "$full" ]; then
        mkdir -p "$(dirname "$BACKUP_DIR/$path")"
        cp -r "$full" "$BACKUP_DIR/$path" 2>/dev/null || true
        log "  Backed up: $path"
    else
        warn "  No encontrado (omitiendo): $path"
    fi
}

restore_path() {
    local path="$1"
    local backup="$BACKUP_DIR/$path"
    local full="$REPO_DIR/$path"
    if [ -e "$backup" ]; then
        mkdir -p "$(dirname "$full")"
        if [ -d "$backup" ]; then
            mkdir -p "$full"
            cp -r "$backup/." "$full/"
        else
            cp "$backup" "$full"
        fi
        log "  Restaurado: $path"
    fi
}

# Respalda .env, memoria/ y el .py principal de TODOS los sub-agentes en carpeta.
# Detecta automáticamente cualquier agente creado en runtime, sin necesidad de
# listarlo manualmente aquí.
backup_all_sub_agents() {
    local sub_agents_dir="$REPO_DIR/agent_core/sub_agents"
    local count=0
    for agent_dir in "$sub_agents_dir"/*/; do
        [ -d "$agent_dir" ] || continue
        local agent_name
        agent_name="$(basename "$agent_dir")"
        # Ignorar __pycache__ y similares
        [[ "$agent_name" == __* ]] && continue

        local backed=0
        # .env del agente
        if [ -f "$agent_dir/.env" ]; then
            backup_path "agent_core/sub_agents/$agent_name/.env"
            backed=1
        fi
        # Carpeta de memoria completa
        if [ -d "$agent_dir/memoria" ]; then
            backup_path "agent_core/sub_agents/$agent_name/memoria"
            backed=1
        fi
        # Archivo Python principal (preserva agentes creados en runtime que no están en git)
        local py_file="$agent_dir/${agent_name}_agent.py"
        if [ -f "$py_file" ]; then
            backup_path "agent_core/sub_agents/$agent_name/${agent_name}_agent.py"
            backed=1
        fi
        [ $backed -eq 1 ] && ((count++)) || true
    done
    log "  $count sub-agente(s) en carpeta respaldado(s)."
}

# Restaura .env, memoria/ y .py de TODOS los sub-agentes que estén en el backup.
restore_all_sub_agents() {
    local backup_sub="$BACKUP_DIR/agent_core/sub_agents"
    [ -d "$backup_sub" ] || return 0
    local count=0
    for agent_dir in "$backup_sub"/*/; do
        [ -d "$agent_dir" ] || continue
        local agent_name
        agent_name="$(basename "$agent_dir")"
        [[ "$agent_name" == __* ]] && continue

        restore_path "agent_core/sub_agents/$agent_name/.env" 2>/dev/null || true
        restore_path "agent_core/sub_agents/$agent_name/memoria" 2>/dev/null || true
        restore_path "agent_core/sub_agents/$agent_name/${agent_name}_agent.py" 2>/dev/null || true
        ((count++)) || true
    done
    log "  $count sub-agente(s) en carpeta restaurado(s)."
}

cd "$REPO_DIR"
log "=== Iniciando deploy en: $REPO_DIR ==="
mkdir -p "$BACKUP_DIR"

# ─── 1. Backup de datos de producción ────────────────────────────────────────
log "Respaldando datos de producción en $BACKUP_DIR ..."
backup_path "agent_core/config"
backup_path "agent_core/keys"
backup_path "agent_core/memoria"
backup_path "agent_core/.env"
backup_path "agent_core/mcp_config.yaml"
# Auto-descubre y respalda TODOS los sub-agentes en carpeta
backup_all_sub_agents

# ─── 2. Git stash ────────────────────────────────────────────────────────────
log "Guardando cambios locales sin commitear ..."
git stash push --include-untracked -m "deploy-stash-$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true

# ─── 3. Git pull ─────────────────────────────────────────────────────────────
log "Haciendo git pull ..."
git pull origin main || error "¡Falló el git pull! Revisa conflictos."
log "Pull exitoso."

# ─── 4. Restaurar datos de producción ────────────────────────────────────────
log "Restaurando datos de producción ..."
restore_path "agent_core/config"
restore_path "agent_core/keys"
restore_path "agent_core/memoria"

log "Protegiendo y reorganizando bases SQLite hacia memoria/bds/ ..."
mkdir -p "$REPO_DIR/agent_core/memoria/bds"
find "$REPO_DIR/agent_core/memoria" -maxdepth 1 -name "*.db*" -exec mv {} "$REPO_DIR/agent_core/memoria/bds/" \; 2>/dev/null || true

restore_path "agent_core/.env"
backup_path "agent_core/mcp_config.yaml"
# Restaura automáticamente todos los sub-agentes respaldados
restore_all_sub_agents

# ─── 5. Rebuild Docker ───────────────────────────────────────────────────────
if [ "$1" != "--no-build" ]; then
    log "Reconstruyendo contenedores Docker ..."
    docker compose up -d --no-deps --build leygo-bot leygo-gui
    log "Contenedores actualizados."
else
    warn "Saltando rebuilds (--no-build)."
    warn "Para aplicar: docker compose up -d --no-deps --build leygo-bot leygo-gui"
fi

# ─── 6. Limpieza ─────────────────────────────────────────────────────────────
rm -rf "$BACKUP_DIR"

log "=== ✅ Deploy completado exitosamente ==="