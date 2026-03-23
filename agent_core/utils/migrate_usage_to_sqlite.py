#!/usr/bin/env python3
"""
Script de migración: usage_history.json → usage.db (SQLite)

Uso:
    python agent_core/utils/migrate_usage_to_sqlite.py

Este script:
1. Lee todos los registros del archivo JSON existente
2. Los inserta en la base de datos SQLite (usage.db)
3. Verifica la integridad comparando conteos
4. Renombra el JSON viejo a .json.bak (no lo borra)

Es seguro ejecutarlo múltiples veces: detecta duplicados por timestamp+model.
"""

import json
import sqlite3
import os
import sys

# Resolver paths relativos al script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENT_CORE_DIR = os.path.dirname(SCRIPT_DIR)
MEMORIA_DIR = os.path.join(AGENT_CORE_DIR, "memoria")

JSON_PATH = os.path.join(MEMORIA_DIR, "usage_history.json")
DB_PATH = os.path.join(MEMORIA_DIR, "usage.db")


def migrate():
    print("=" * 60)
    print("  Migración: usage_history.json → usage.db (SQLite)")
    print("=" * 60)
    
    # ── 1. Verificar que existe el JSON ──────────────────────────
    if not os.path.exists(JSON_PATH):
        print(f"\n❌ No se encontró el archivo JSON en:\n   {JSON_PATH}")
        print("   No hay nada que migrar.")
        return
    
    # ── 2. Leer JSON ─────────────────────────────────────────────
    print(f"\n📂 Leyendo: {JSON_PATH}")
    try:
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                print("   El archivo está vacío. Nada que migrar.")
                return
            records = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"   ❌ Error al parsear el JSON: {e}")
        print("   Intenta reparar el archivo manualmente antes de migrar.")
        return
    
    total_json = len(records)
    print(f"   ✅ {total_json} registros encontrados en el JSON.")
    
    # ── 3. Crear/conectar SQLite ─────────────────────────────────
    print(f"\n🗄️  Conectando a: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS usage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_input TEXT,
            model TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cost_usd REAL DEFAULT 0.0,
            thread_id TEXT DEFAULT 'system'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_history(timestamp)")
    conn.commit()
    
    # ── 4. Contar registros existentes en SQLite ─────────────────
    existing_count = conn.execute("SELECT COUNT(*) FROM usage_history").fetchone()[0]
    print(f"   📊 Registros existentes en SQLite: {existing_count}")
    
    # ── 5. Insertar registros ────────────────────────────────────
    inserted = 0
    skipped = 0
    errors = 0
    
    print(f"\n🔄 Migrando {total_json} registros...")
    
    for i, record in enumerate(records):
        try:
            ts = record.get("timestamp", "")
            model = record.get("model", "")
            user_input = record.get("user_input", "")
            input_tokens = record.get("input_tokens", 0)
            output_tokens = record.get("output_tokens", 0)
            cost_usd = record.get("cost_usd", 0.0)
            thread_id = record.get("thread_id", "system")
            
            # Check duplicado por timestamp + model + input_tokens
            dup = conn.execute(
                "SELECT COUNT(*) FROM usage_history WHERE timestamp = ? AND model = ? AND input_tokens = ?",
                (ts, model, input_tokens)
            ).fetchone()[0]
            
            if dup > 0:
                skipped += 1
                continue
            
            conn.execute(
                "INSERT INTO usage_history (timestamp, user_input, model, input_tokens, output_tokens, cost_usd, thread_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, user_input, model, input_tokens, output_tokens, cost_usd, thread_id)
            )
            inserted += 1
            
        except Exception as e:
            errors += 1
            print(f"   ⚠️  Error en registro #{i}: {e}")
    
    conn.commit()
    
    # ── 6. Verificación ──────────────────────────────────────────
    final_count = conn.execute("SELECT COUNT(*) FROM usage_history").fetchone()[0]
    total_cost = conn.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM usage_history").fetchone()[0]
    conn.close()
    
    print(f"\n{'=' * 60}")
    print(f"  📊 Resultado de la migración:")
    print(f"{'=' * 60}")
    print(f"  Registros en JSON:      {total_json}")
    print(f"  Insertados en SQLite:   {inserted}")
    print(f"  Duplicados omitidos:    {skipped}")
    print(f"  Errores:                {errors}")
    print(f"  Total final en SQLite:  {final_count}")
    print(f"  Costo total registrado: ${total_cost:.4f} USD")
    print(f"{'=' * 60}")
    
    # ── 7. Backup del JSON viejo ─────────────────────────────────
    if inserted > 0 or skipped == total_json:
        backup_path = JSON_PATH + ".bak"
        if not os.path.exists(backup_path):
            os.rename(JSON_PATH, backup_path)
            print(f"\n📦 JSON respaldado como: {backup_path}")
        else:
            print(f"\n📦 Backup ya existía: {backup_path}")
            print(f"   El JSON original se conserva en: {JSON_PATH}")
            print(f"   Puedes borrarlo manualmente si todo está correcto.")
    
    print("\n✅ Migración completada exitosamente.\n")


if __name__ == "__main__":
    migrate()
