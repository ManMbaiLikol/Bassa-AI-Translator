"""Tests pour l'API /api/stats."""
import pytest
from backend.models.history import TranslationHistory
from backend.models.dictionary import DictionaryEntry
from backend.models.corpus import CorpusPair
from backend.models.user import UserRole
from tests.conftest import TestingSessionLocal


def _register_and_login(client, username, email, password="pass1234"):
    client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _promote(username, role):
    db = TestingSessionLocal()
    from backend.models.user import User
    u = db.query(User).filter_by(username=username).first()
    u.role = role
    db.commit()
    db.close()


def _seed_history(db, n=3, engine="dictionary", lang="fr", user_id=None):
    for i in range(n):
        db.add(TranslationHistory(
            user_id=user_id,
            source_language=lang,
            source_text=f"Texte {i}",
            translated_text=f"Bassa {i}",
            engine=engine,
            confidence=0.6,
        ))
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/stats
# ─────────────────────────────────────────────────────────────────────────────

class TestGlobalStats:

    def test_stats_public_no_auth(self, client):
        """Stats accessibles sans authentification."""
        resp = client.get("/api/stats")
        assert resp.status_code == 200

    def test_stats_structure(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert "translations" in data
        assert "dictionary" in data
        assert "corpus" in data
        assert "contributions" in data

    def test_stats_translations_section(self, client):
        resp = client.get("/api/stats")
        t = resp.json()["translations"]
        assert "total" in t
        assert "today" in t
        assert "by_engine" in t
        assert "by_language" in t

    def test_stats_count_history(self, client, db):
        _seed_history(db, n=5, engine="dictionary", lang="fr")
        _seed_history(db, n=3, engine="ml", lang="en")

        resp = client.get("/api/stats")
        data = resp.json()
        assert data["translations"]["total"] == 8
        assert data["translations"]["by_engine"]["dictionary"] == 5
        assert data["translations"]["by_engine"]["ml"] == 3
        assert data["translations"]["by_language"]["fr"] == 5
        assert data["translations"]["by_language"]["en"] == 3

    def test_stats_dictionary_counts(self, client, db):
        db.add(DictionaryEntry(source_language="fr", source_word="bonjour", bassa_word="Mbolo", is_verified=True))
        db.add(DictionaryEntry(source_language="fr", source_word="merci", bassa_word="A ngi nyu", is_verified=False))
        db.commit()

        resp = client.get("/api/stats")
        d = resp.json()["dictionary"]
        assert d["total"] == 2
        assert d["verified"] == 1

    def test_stats_corpus_counts(self, client, db):
        db.add(CorpusPair(source_language="fr", source_text="Bonjour monde", bassa_text="Mbolo bena", is_verified=True))
        db.add(CorpusPair(source_language="fr", source_text="Au revoir", bassa_text="Bolo", is_verified=False))
        db.commit()

        resp = client.get("/api/stats")
        c = resp.json()["corpus"]
        assert c["total"] == 2
        assert c["verified"] == 1

    def test_stats_empty_db(self, client):
        resp = client.get("/api/stats")
        data = resp.json()
        assert data["translations"]["total"] == 0
        assert data["translations"]["by_engine"] == {}
        assert data["translations"]["by_language"] == {}

    def test_translate_increments_stats(self, client, db):
        """Traduire via l'API doit incrémenter les stats."""
        before = client.get("/api/stats").json()["translations"]["total"]
        client.post("/api/translate", json={"text": "Bonjour", "source_language": "fr"})
        after = client.get("/api/stats").json()["translations"]["total"]
        assert after == before + 1


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/stats/activity
# ─────────────────────────────────────────────────────────────────────────────

class TestActivityStats:

    def test_activity_requires_admin(self, client):
        """L'endpoint activity nécessite le rôle admin."""
        resp = client.get("/api/stats/activity")
        assert resp.status_code == 401

        token = _register_and_login(client, "contrib_act", "contrib_act@test.com")
        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_activity_admin_access(self, client):
        token = _register_and_login(client, "admin_act", "admin_act@test.com")
        _promote("admin_act", UserRole.admin)
        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_activity_structure(self, client):
        token = _register_and_login(client, "admin_str", "admin_str@test.com")
        _promote("admin_str", UserRole.admin)
        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert "period_days" in data
        assert "translations_per_day" in data
        assert "top_engines" in data
        assert "avg_confidence_by_engine" in data

    def test_activity_default_7_days(self, client):
        token = _register_and_login(client, "admin_7d", "admin_7d@test.com")
        _promote("admin_7d", UserRole.admin)
        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["period_days"] == 7

    def test_activity_custom_days(self, client):
        token = _register_and_login(client, "admin_30", "admin_30@test.com")
        _promote("admin_30", UserRole.admin)
        resp = client.get("/api/stats/activity?days=30", headers={"Authorization": f"Bearer {token}"})
        assert resp.json()["period_days"] == 30

    def test_activity_invalid_days(self, client):
        token = _register_and_login(client, "admin_inv", "admin_inv@test.com")
        _promote("admin_inv", UserRole.admin)
        resp = client.get("/api/stats/activity?days=200", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422

    def test_activity_top_engines(self, client, db):
        token = _register_and_login(client, "admin_eng", "admin_eng@test.com")
        _promote("admin_eng", UserRole.admin)
        _seed_history(db, n=5, engine="dictionary")
        _seed_history(db, n=3, engine="ml")

        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        top = resp.json()["top_engines"]
        # dictionary doit être le premier moteur (5 > 3)
        assert top[0]["engine"] == "dictionary"
        assert top[0]["count"] == 5

    def test_activity_avg_confidence(self, client, db):
        token = _register_and_login(client, "admin_conf", "admin_conf@test.com")
        _promote("admin_conf", UserRole.admin)
        _seed_history(db, n=2, engine="ml")

        resp = client.get("/api/stats/activity", headers={"Authorization": f"Bearer {token}"})
        avg = resp.json()["avg_confidence_by_engine"]
        assert "ml" in avg
        assert avg["ml"] == pytest.approx(0.6, abs=0.01)

    def test_activity_empty_period(self, client):
        token = _register_and_login(client, "admin_emp", "admin_emp@test.com")
        _promote("admin_emp", UserRole.admin)
        resp = client.get("/api/stats/activity?days=1", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["translations_per_day"] == []
        assert data["top_engines"] == []
