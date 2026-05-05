import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import Base, get_db
from backend.engine.base import TranslationEngine, TranslationResult, WordTranslation
from backend.api import translate

# SQLite en mémoire avec StaticPool : isolation totale, pas de fichier résiduel,
# toutes les connexions partagent la même DB (nécessaire pour que les sessions
# des moteurs de traduction voient les données insérées par le test).
SQLALCHEMY_TEST_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_TEST_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class FakeEngine(TranslationEngine):
    """Minimal engine for testing that doesn't need MySQL."""
    def translate(self, text: str, source_language: str) -> TranslationResult:
        return TranslationResult(
            source_text=text,
            translated_text=text,
            source_language=source_language,
            confidence=0.5,
            word_translations=[WordTranslation(source=text, translated=text, found=False)],
            engine="test",
        )

    def reload(self) -> None:
        pass


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Import app after overrides are ready
from backend.main import app

app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Vide les compteurs de rate limit entre chaque test (stockage mémoire)."""
    from backend.rate_limit import limiter
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    Base.metadata.create_all(bind=engine)
    # Set up a fake translation engine for tests
    fake = FakeEngine()
    translate.register_engine("dictionary", fake)
    translate.register_engine("ml", fake)
    translate.register_engine("llm", fake)
    translate.set_default_engine("dictionary")
    yield TestClient(app, raise_server_exceptions=False)
    Base.metadata.drop_all(bind=engine)
