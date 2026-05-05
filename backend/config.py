from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    DATABASE_URL: str = "mysql+pymysql://root:@localhost:3306/bassa_translator?charset=utf8mb4"
    SECRET_KEY: str = "change-this-to-a-random-secret-key-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # Moteur de traduction actif: "dictionary" | "ml" | "llm" | "auto"
    # auto = llm si clé API présente, sinon ml si sentence-transformers dispo, sinon dictionary
    ENGINE_TYPE: str = "auto"

    # Clé API Anthropic (Claude) pour le moteur LLM
    ANTHROPIC_API_KEY: str = ""

    # Modèle Claude : haiku (rapide/économique) ou sonnet (meilleure qualité)
    # claude-haiku-4-5-20251001 | claude-sonnet-4-6
    CLAUDE_MODEL: str = "claude-haiku-4-5-20251001"

    # Google OAuth (laisser vide pour désactiver)
    GOOGLE_CLIENT_ID: str = ""

    # CORS — origines autorisées (séparées par des virgules)
    # Prod : https://ton-domaine.com
    # Dev  : http://localhost:8000,http://127.0.0.1:8000
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # Modèle Sentence-Transformers pour les embeddings multilingues
    ML_EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Seuils de confiance pour le moteur ML (retrieval)
    # Au-dessus de HIGH_THRESHOLD -> retourner la traduction du corpus directement
    # Entre MED et HIGH -> suggérer la traduction du corpus en supplément
    ML_HIGH_THRESHOLD: float = 0.82
    ML_MED_THRESHOLD: float = 0.70

    # Moteur NMT (MarianMT fine-tuné fr→Bassa)
    # Dossier contenant le modèle entraîné par scripts/train_nmt.py
    NMT_MODEL_DIR: str = ""          # vide = chemin par défaut (backend/models_cache/nmt_fr_bassa)
    NMT_BASE_MODEL: str = "Helsinki-NLP/opus-mt-fr-kg"

    model_config = {"env_file": str(Path(__file__).resolve().parent.parent / ".env")}


settings = Settings()
