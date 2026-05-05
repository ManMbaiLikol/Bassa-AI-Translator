"""Tests pour l'API /api/history et l'enregistrement automatique."""
import pytest
from backend.models.history import TranslationHistory
from backend.models.user import User, UserRole
from tests.conftest import TestingSessionLocal


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _register_and_login(client, username, email, password="pass1234"):
    client.post("/api/auth/register", json={"username": username, "email": email, "password": password})
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def _promote(username, role: UserRole):
    db = TestingSessionLocal()
    u = db.query(User).filter_by(username=username).first()
    u.role = role
    db.commit()
    db.close()


def _seed_history(db, user_id, n=3, lang="fr", engine="dictionary"):
    for i in range(n):
        db.add(TranslationHistory(
            user_id=user_id,
            source_language=lang,
            source_text=f"Phrase {i}",
            translated_text=f"Bassa {i}",
            engine=engine,
            confidence=0.5 + i * 0.1,
        ))
    db.commit()


def _get_user_id(username):
    db = TestingSessionLocal()
    u = db.query(User).filter_by(username=username).first()
    uid = u.id
    db.close()
    return uid


# ─────────────────────────────────────────────────────────────────────────────
# Enregistrement automatique lors de la traduction
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryAutoRecord:

    def test_translate_records_anonymous(self, client, db):
        """Une traduction anonyme est enregistrée avec user_id=None."""
        client.post("/api/translate", json={"text": "Bonjour", "source_language": "fr"})
        entries = db.query(TranslationHistory).all()
        assert len(entries) == 1
        assert entries[0].user_id is None
        assert entries[0].source_text == "Bonjour"

    def test_translate_records_authenticated_user(self, client, db):
        """Une traduction authentifiée enregistre le user_id."""
        token = _register_and_login(client, "user1", "u1@test.com")
        uid = _get_user_id("user1")
        client.post(
            "/api/translate",
            json={"text": "Bonjour", "source_language": "fr"},
            headers={"Authorization": f"Bearer {token}"},
        )
        entry = db.query(TranslationHistory).filter_by(user_id=uid).first()
        assert entry is not None
        assert entry.source_text == "Bonjour"

    def test_translate_records_engine(self, client, db):
        """Le moteur utilisé est correctement enregistré."""
        client.post("/api/translate", json={"text": "Bonjour", "source_language": "fr"})
        entry = db.query(TranslationHistory).first()
        assert entry.engine in ("dictionary", "ml", "llm", "test")

    def test_translate_records_confidence(self, client, db):
        """La confiance est enregistrée (ou None si 0)."""
        client.post("/api/translate", json={"text": "Bonjour", "source_language": "fr"})
        entry = db.query(TranslationHistory).first()
        # confidence peut être None ou un float
        assert entry.confidence is None or isinstance(entry.confidence, float)

    def test_multiple_translates_create_multiple_entries(self, client, db):
        client.post("/api/translate", json={"text": "Bonjour", "source_language": "fr"})
        client.post("/api/translate", json={"text": "Merci", "source_language": "fr"})
        assert db.query(TranslationHistory).count() == 2


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/history
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryList:

    def test_requires_auth(self, client):
        resp = client.get("/api/history")
        assert resp.status_code == 401

    def test_user_sees_only_own(self, client, db):
        token1 = _register_and_login(client, "alice", "alice@test.com")
        token2 = _register_and_login(client, "bob", "bob@test.com")
        uid1 = _get_user_id("alice")
        uid2 = _get_user_id("bob")

        _seed_history(db, uid1, n=3)
        _seed_history(db, uid2, n=2)

        resp = client.get("/api/history", headers={"Authorization": f"Bearer {token1}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert all(e["user_id"] == uid1 for e in data["items"])

    def test_admin_sees_all(self, client, db):
        token = _register_and_login(client, "admin_h", "admin_h@test.com")
        _promote("admin_h", UserRole.admin)
        uid = _get_user_id("admin_h")
        _seed_history(db, uid, n=2)
        _seed_history(db, None, n=1)  # anonyme

        resp = client.get("/api/history", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["total"] == 3

    def test_pagination(self, client, db):
        token = _register_and_login(client, "paguser", "pag@test.com")
        uid = _get_user_id("paguser")
        _seed_history(db, uid, n=15)

        resp = client.get("/api/history?page=1&size=5", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["total"] == 15
        assert len(data["items"]) == 5
        assert data["pages"] == 3

    def test_filter_by_lang(self, client, db):
        token = _register_and_login(client, "languser", "lang@test.com")
        uid = _get_user_id("languser")
        _seed_history(db, uid, n=3, lang="fr")
        _seed_history(db, uid, n=2, lang="en")

        resp = client.get("/api/history?lang=fr", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["total"] == 3
        assert all(e["source_language"] == "fr" for e in data["items"])

    def test_filter_by_engine(self, client, db):
        token = _register_and_login(client, "enguser", "eng@test.com")
        uid = _get_user_id("enguser")
        _seed_history(db, uid, n=3, engine="dictionary")
        _seed_history(db, uid, n=2, engine="ml")

        resp = client.get("/api/history?engine=ml", headers={"Authorization": f"Bearer {token}"})
        data = resp.json()
        assert data["total"] == 2

    def test_ordered_by_recent_first(self, client, db):
        from datetime import datetime, timedelta, timezone
        token = _register_and_login(client, "orduser", "ord@test.com")
        uid = _get_user_id("orduser")
        now = datetime.now(timezone.utc)
        # Insérer du plus ancien au plus récent → IDs croissants, dates croissantes
        for i in range(3):
            db.add(TranslationHistory(
                user_id=uid,
                source_language="fr",
                source_text=f"Phrase {i}",
                translated_text=f"Bassa {i}",
                engine="dictionary",
                confidence=0.5,
                created_at=now - timedelta(hours=2 - i),  # i=0 oldest, i=2 newest
            ))
        db.commit()

        resp = client.get("/api/history", headers={"Authorization": f"Bearer {token}"})
        items = resp.json()["items"]
        # ORDER BY created_at DESC : entrée la plus récente (ID le plus haut) en premier
        ids = [i["id"] for i in items]
        assert ids == sorted(ids, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/history/{id}
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryDeleteEntry:

    def test_user_can_delete_own(self, client, db):
        token = _register_and_login(client, "delu", "delu@test.com")
        uid = _get_user_id("delu")
        _seed_history(db, uid, n=1)
        entry_id = db.query(TranslationHistory).filter_by(user_id=uid).first().id

        resp = client.delete(f"/api/history/{entry_id}", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 204
        assert db.query(TranslationHistory).filter_by(id=entry_id).first() is None

    def test_user_cannot_delete_others(self, client, db):
        token_a = _register_and_login(client, "del_a", "del_a@test.com")
        token_b = _register_and_login(client, "del_b", "del_b@test.com")
        uid_a = _get_user_id("del_a")
        _seed_history(db, uid_a, n=1)
        entry_id = db.query(TranslationHistory).filter_by(user_id=uid_a).first().id

        resp = client.delete(f"/api/history/{entry_id}", headers={"Authorization": f"Bearer {token_b}"})
        assert resp.status_code == 403

    def test_admin_can_delete_any(self, client, db):
        token_admin = _register_and_login(client, "del_admin", "del_admin@test.com")
        _promote("del_admin", UserRole.admin)
        uid_other = _get_user_id("del_admin")
        _seed_history(db, uid_other, n=1)
        entry_id = db.query(TranslationHistory).filter_by(user_id=uid_other).first().id

        resp = client.delete(f"/api/history/{entry_id}", headers={"Authorization": f"Bearer {token_admin}"})
        assert resp.status_code == 204

    def test_delete_not_found(self, client):
        token = _register_and_login(client, "delnf", "delnf@test.com")
        resp = client.delete("/api/history/9999", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.delete("/api/history/1")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /api/history  (vider)
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryClear:

    def test_clears_own_history(self, client, db):
        token = _register_and_login(client, "clr", "clr@test.com")
        uid = _get_user_id("clr")
        _seed_history(db, uid, n=5)
        assert db.query(TranslationHistory).filter_by(user_id=uid).count() == 5

        resp = client.delete("/api/history", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 204
        assert db.query(TranslationHistory).filter_by(user_id=uid).count() == 0

    def test_does_not_delete_others(self, client, db):
        token_a = _register_and_login(client, "clr_a", "clr_a@test.com")
        _register_and_login(client, "clr_b", "clr_b@test.com")
        uid_a = _get_user_id("clr_a")
        uid_b = _get_user_id("clr_b")
        _seed_history(db, uid_a, n=3)
        _seed_history(db, uid_b, n=2)

        client.delete("/api/history", headers={"Authorization": f"Bearer {token_a}"})
        assert db.query(TranslationHistory).filter_by(user_id=uid_b).count() == 2

    def test_requires_auth(self, client):
        resp = client.delete("/api/history")
        assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/history/export
# ─────────────────────────────────────────────────────────────────────────────

class TestHistoryExport:

    def test_export_csv(self, client, db):
        token = _register_and_login(client, "exp_u", "exp_u@test.com")
        uid = _get_user_id("exp_u")
        _seed_history(db, uid, n=2)

        resp = client.get("/api/history/export", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        assert len(lines) == 3  # header + 2 entrées

    def test_export_filter_lang(self, client, db):
        token = _register_and_login(client, "exp_l", "exp_l@test.com")
        uid = _get_user_id("exp_l")
        _seed_history(db, uid, n=3, lang="fr")
        _seed_history(db, uid, n=2, lang="en")

        resp = client.get("/api/history/export?lang=en", headers={"Authorization": f"Bearer {token}"})
        lines = resp.text.strip().split("\n")
        assert len(lines) == 3  # header + 2

    def test_export_requires_auth(self, client):
        resp = client.get("/api/history/export")
        assert resp.status_code == 401

    def test_export_only_own(self, client, db):
        token_a = _register_and_login(client, "exp_a", "exp_a@test.com")
        _register_and_login(client, "exp_b", "exp_b@test.com")
        uid_a = _get_user_id("exp_a")
        uid_b = _get_user_id("exp_b")
        _seed_history(db, uid_a, n=2)
        _seed_history(db, uid_b, n=5)

        resp = client.get("/api/history/export", headers={"Authorization": f"Bearer {token_a}"})
        lines = resp.text.strip().split("\n")
        assert len(lines) == 3  # header + 2 (uniquement les siennes)
