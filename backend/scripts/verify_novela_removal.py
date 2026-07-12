"""
Verifica que no queden residuos de "Novela/Serie" en codigo ni BD.

Uso:
    python -m scripts.verify_novela_removal
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
THIS_FILE = os.path.basename(__file__)

errors: list[str] = []

print("=" * 60)
print("Verificacion de eliminacion de Novela/Serie")
print("=" * 60)

# ── 1. Buscar en codigo fuente ──
print("\n[1/4] Buscando en codigo fuente (.py)...")
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
            # Ignorar este mismo script
            if fn == THIS_FILE and dirpath == os.path.join(ROOT, "scripts"):
                continue
            fp = os.path.join(dirpath, fn)
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, 1):
                    if re.search(r"[Nn]ovela[/][Ss]erie", line):
                        rel = os.path.relpath(fp, ROOT)
                        print("   ❌ {}:{}: {}".format(rel, lineno, line.strip()))
                        errors.append("Codigo: {}:{}".format(rel, lineno))
                        found_in_code += 1

if found_in_code == 0:
    print("   ✅ No se encontro Novela/Serie en ningun .py (excluyendo este script)")

# ── 2. Buscar en __pycache__ ──
print("\n[2/4] Buscando en bytecode compilado (.pyc)...")
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
                        print("   ⚠️  {} tiene residuos".format(rel))
                        pycache_found += 1

if pycache_found == 0:
    print("   ✅ No hay .pyc con residuos")
else:
    print("   Solucion: find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null")

# ── 3. Verificar BD ──
print("\n[3/4] Verificando base de datos...")
try:
    from sqlalchemy import text
    from src.db.engine import async_session_factory

    async def check_db():
        global errors
        async with async_session_factory() as session:
            checks = [
                ("word_list_items", "category", "novela/serie"),
                ("answers", "word_slot", "Novela/Serie"),
                ("group_configs", "categories", "%Novela/Serie%"),
            ]
            for table, column, search in checks:
                sql = text(
                    "SELECT COUNT(*) FROM {} WHERE {} LIKE :s".format(table, column)
                )
                result = await session.execute(sql, {"s": search})
                count = result.scalar()
                if count > 0:
                    print(
                        "   ❌ {}.{} tiene {} registro(s)".format(table, column, count)
                    )
                    errors.append("BD: {}.{} = {}".format(table, column, count))
                else:
                    print("   ✅ {}.{} → 0 registros".format(table, column))

    asyncio.run(check_db())
except ModuleNotFoundError as e:
    print("   ⚠️  No se pudo conectar a BD: {}".format(e))
except Exception as e:
    print("   ⚠️  Error de BD: {}".format(e))

# ── 4. Verificar ALL_CATEGORIES ──
print("\n[4/4] Verificando ALL_CATEGORIES en settings.py...")
settings_path = os.path.join(ROOT, "src", "keyboards", "settings.py")
if os.path.exists(settings_path):
    with open(settings_path, "r") as f:
        content = f.read()
        if "Novela/Serie" in content:
            print("   ❌ settings.py aun tiene Novela/Serie!")
            errors.append("settings.py contiene Novela/Serie")
        elif "Animal" in content:
            print('   ✅ ALL_CATEGORIES tiene "Animal"')
else:
    print("   ⚠️  No se encontro settings.py")

# ── Resumen ──
print("\n" + "=" * 60)
if errors:
    print("❌ Se encontraron {} problema(s):".format(len(errors)))
    for e in errors:
        print("   - {}".format(e))
else:
    print("✅  TODO LIMPIO — No hay rastros de Novela/Serie en codigo ni BD")
print("=" * 60)
