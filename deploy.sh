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

cd "$REPO_DIR"
log "=== Iniciando deploy en: $REPO_DIR ==="
mkdir -p "$BACKUP_DIR"

# ─── 1. Backup de datos de producción ────────────────────────────────────────
log "Respaldando datos de producción en $BACKUP_DIR ..."
backup_path "agent_core/config"
backup_path "agent_core/keys"
backup_path "agent_core/memoria"
backup_path "agent_core/.env"
backup_path "agent_core/sub_agents/nami/.env"
backup_path "agent_core/sub_agents/nami/memoria"
backup_path "agent_core/sub_agents/chart/.env"
backup_path "agent_core/sub_agents/twitter_reader/.env"
backup_path "agent_core/sub_agents/nanobanana/.env"
backup_path "agent_core/sub_agents/youtube_analyzer/.env"
backup_path "agent_core/sub_agents/youtube_analyzer/memoria"

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
restore_path "agent_core/.env"
restore_path "agent_core/sub_agents/nami/.env"
restore_path "agent_core/sub_agents/nami/memoria"
restore_path "agent_core/sub_agents/chart/.env"
restore_path "agent_core/sub_agents/twitter_reader/.env"
restore_path "agent_core/sub_agents/nanobanana/.env"
restore_path "agent_core/sub_agents/youtube_analyzer/.env"
restore_path "agent_core/sub_agents/youtube_analyzer/memoria"

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