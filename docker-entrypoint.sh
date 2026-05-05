#!/bin/bash
set -e

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

for attempt in range(30):
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database)
        conn.close()
        print(f"Base disponible ({host}:{port}).")
        sys.exit(0)
    except Exception as e:
        print(f"Tentative {attempt+1}/30 : {e}")
        time.sleep(2)

print("ERREUR : base inaccessible après 30 tentatives.")
sys.exit(1)
EOF

echo "==> Migrations Alembic..."
alembic upgrade head

echo "==> Démarrage du serveur..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
