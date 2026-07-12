"""
Verifica que no queden residuos de "Novela/Serie" en código ni BD.

Uso: python -m scripts.verify_novela_removal
"""

import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

errors: list[str] = []

print("=" * 60)
print("🔍 Verificación de eliminación de Novela/Serie")
print("=" * 60)

# ── 1. Buscar en código fuente ──
print("\n📁 1. Buscando en código fuente (.py)...")
source_dirs = [
    os.path.join(ROOT, "src"),
    os.path.join(ROOT, "scripts"),
    os.path.join(ROOT, "tests"),
]
found_in_code = 0
for sd in source_dirs:
    if not os.path.isdir(sd):
        continue
    for dirpath, _, filenames in os.walk(sd):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if re.search(r"[Nn]ovela[/][Ss]erie", line):
                        rel = os.path.relpath(fp, ROOT)
                        print(f"   ❌ {rel}:{lineno}: {line.strip()}")
                        errors.append(f"Código: {rel}:{lineno}")
                        found_in_code += 1

if found_in_code == 0:
    print("   ✅ No se encontró 'Novela/Serie' en ningún .py")

# ── 2. Buscar en archivos .md de phases ──
print("\n📁 2. Buscando en archivos .md...")
phases_dir = os.path.join(os.path.dirname(ROOT), "phases")
found_in_md = 0
if os.path.isdir(phases_dir):
    for fn in os.listdir(phases_dir):
        if not fn.endswith(".md"):
            continue
        fp = os.path.join(phases_dir, fn)
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            for lineno, line in enumerate(f, 1):
                if re.search(r"[Nn]ovela[/][Ss]erie", line):
                    print(f"   ⚠️  {fn}:{lineno}: {line.strip()}")
                    found_in_md += 1
    if found_in_md == 0:
        print("   ✅ No se encontró en .md")
    else:
        print(f"   ⚠️  {found_in_md} menciones en docs (opcional, no afecta al bot)")
else:
    print("   ⏭️  No hay carpeta phases/ (solo local)")

# ── 3. Buscar en __pycache__ archivos .pyc compilados ──
print("\n📁 3. Buscando en bytecode compilado (.pyc en __pycache__)...")
import compileall
pycache_found = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    if "__pycache__" in dirpath:
        for fn in filenames:
            if fn.endswith(".pyc"):
                fp = os.path.join(dirpath, fn)
                with open(fp, "rb") as f:
                    content = f.read()
                    if b"Novela" in content or b"novela" in content:
                        rel = os.path.relpath(fp, ROOT)
                        print(f"   ⚠️  {rel} contiene residuos de Novela")
                        pycache_found += 1

if pycache_found == 0:
    print("   ✅ No hay .pyc con residuos")

# ── 4. Conectar a BD local y verificar ──
print("\n🗄️  4. Verificando base de datos local...")
try:
    from src.db.engine import async_session_factory
    from sqlalchemy import text
    import asyncio

    async def check_db():
        global errors
        async with async_session_factory() as session:
            for table, column, search in [
                ("word_list_items", "category", "'novela/serie'"),
                ("word_list_items", "category", "'Novela/Serie'"),
                ("answers", "word_slot", "'Novela/Serie'"),
                ("group_configs", "categories", "'%Novela/Serie%'"),
            ]:
                sql = text(f"SELECT COUNT(*) FROM {table} WHERE {column} LIKE {search}")
                result = await session.execute(sql)
                count = result.scalar()
                if count > 0:
                    print(f"   ❌ {table}.{column} tiene {count} registro(s) con Novela/Serie")
                    errors.append(f"BD: {table}.{column} = {count}")
                else:
                    print(f"   ✅ {table}.{column} → 0 registros")

            for table, column in [
                ("word_list_items", "category"),
                ("answers", "word_slot"),
            ]:
                sql = text(f"SELECT DISTINCT {column} FROM {table} ORDER BY {column}")
                result = await session.execute(sql)
                values = [row[0] for row in result]
                print(f"   ℹ️  Valores únicos en {table}.{column}: {values}")

    asyncio.run(check_db())
except Exception as e:
    print(f"   ⚠️  No se pudo conectar a BD local: {e}")

# ── Resumen ──
print("\n" + "=" * 60)
if errors:
    print(f"❌ Se encontraron {len(errors)} problema(s):")
    for e in errors:
        print(f"   - {e}")
else:
    print("✅  TODO LIMPIO — No hay rastros de Novela/Serie en código ni BD local")
print("=" * 60)
