FROM python:3.13-slim

WORKDIR /app

# Dépendances système (gcc pour certains wheels, pkg-config pour mysqlclient)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# PyTorch CPU-only en premier pour éviter le téléchargement de la version CUDA (~2.5 GB)
# La version CPU suffit pour les embeddings sentence-transformers (~800 MB)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Dépendances Python de production
COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

# Code applicatif
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Script de démarrage
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
