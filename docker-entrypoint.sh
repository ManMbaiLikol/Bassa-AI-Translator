#!/bin/bash
set -e

DATABASE_URL="${DATABASE_URL:-}"

if [ -z "$DATABASE_URL" ]; then
    echo "ERREUR : la variable DATABASE_URL n'est pas définie."
    echo "Configurez-la dans Railway : Settings > Variables."
    exit 1
fi

echo "==> Attente de la base de données..."
python - <<'EOF'
import time, sys, pymysql
from urllib.parse import urlparse

url = __import__('os').environ.get('DATABASE_URL', '')
p = urlparse(url)
host = p.hostname or 'db'
port = p.port or 3306
user = p.username or 'bassa'
password = p.password or ''
database = (p.path or '/bassa_translator').lstrip('/')

for attempt in range(60):
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database, connect_timeout=5)
        conn.close()
        print(f"Base disponible ({host}:{port}).")
        sys.exit(0)
    except Exception as e:
        print(f"Tentative {attempt+1}/60 : {e}")
        time.sleep(3)

print("ERREUR : base inaccessible après 60 tentatives.")
sys.exit(1)
EOF

echo "==> Migrations Alembic..."
alembic upgrade head

echo "==> Seed des données initiales..."
python -m backend.seed_all

echo "==> Démarrage du serveur..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
