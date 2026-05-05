"""Tests pour l'API corpus et le service CorpusService."""
import io
import pytest

from backend.models.corpus import CorpusPair
from backend.services import corpus as corpus_service


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_admin(client):
    """Crée un admin et retourne son token."""
    client.post("/api/auth/register", json={
        "username": "admin_corpus",
        "email": "admin_corpus@test.com",
        "password": "secret123",
    })
    # Promouvoir en admin via la DB
    from tests.conftest import TestingSessionLocal
    from backend.models.user import User, UserRole
    db = TestingSessionLocal()
    u = db.query(User).filter_by(username="admin_corpus").first()
    u.role = UserRole.admin
    db.commit()
    db.close()

    resp = client.post("/api/auth/login", json={
        "username": "admin_corpus",
        "password": "secret123",
    })
    return resp.json()["access_token"]


def _make_reviewer(client):
    """Crée un reviewer et retourne son token."""
    client.post("/api/auth/register", json={
        "username": "reviewer_corpus",
        "email": "reviewer_corpus@test.com",
        "password": "secret123",
    })
    from tests.conftest import TestingSessionLocal
    from backend.models.user import User, UserRole
    db = TestingSessionLocal()
    u = db.query(User).filter_by(username="reviewer_corpus").first()
    u.role = UserRole.reviewer
    db.commit()
    db.close()

    resp = client.post("/api/auth/login", json={
        "username": "reviewer_corpus",
        "password": "secret123",
    })
    return resp.json()["access_token"]


def _seed_pair(db, source_text="Bonjour", bassa_text="Mbolo", lang="fr", verified=True):
    pair = CorpusPair(
        source_language=lang,
        source_text=source_text,
        bassa_text=bassa_text,
        is_verified=verified,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair


# ─────────────────────────────────────────────────────────────────────────────
# Tests CorpusService
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusService:

    def test_get_all_verified_empty(self, db):
        pairs = corpus_service.get_all_verified(db)
        assert pairs == []

    def test_get_all_verified_filters_unverified(self, db):
        _seed_pair(db, "Hello", "Mbolo", verified=True)
        _seed_pair(db, "Goodbye", "Bolo", verified=False)
        verified = corpus_service.get_all_verified(db)
        assert len(verified) == 1
        assert verified[0].source_text == "Hello"

    def test_get_all_verified_filters_by_lang(self, db):
        _seed_pair(db, "Bonjour", "Mbolo", lang="fr", verified=True)
        _seed_pair(db, "Hello", "Mbolo", lang="en", verified=True)
        fr_pairs = corpus_service.get_all_verified(db, lang="fr")
        assert len(fr_pairs) == 1
        assert fr_pairs[0].source_language == "fr"

    def test_get_all_includes_unverified(self, db):
        _seed_pair(db, "Bonjour", "Mbolo", verified=True)
        _seed_pair(db, "Au revoir", "Bolo", verified=False)
        all_pairs = corpus_service.get_all(db)
        assert len(all_pairs) == 2

    def test_import_csv_basic(self, db):
        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\nfr,Merci,A ngi nyu\n"
        result = corpus_service.import_csv(db, csv_content)
        db.commit()
        assert result.imported == 2
        assert result.skipped == 0
        assert result.errors == []
        assert db.query(CorpusPair).count() == 2

    def test_import_csv_skip_duplicates(self, db):
        _seed_pair(db, "Bonjour", "Mbolo", lang="fr")
        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\nfr,Merci,A ngi nyu\n"
        result = corpus_service.import_csv(db, csv_content)
        db.commit()
        assert result.imported == 1
        assert result.skipped == 1  # doublon ignoré

    def test_import_csv_default_lang(self, db):
        csv_content = "source_text,bassa_text\nHello,Mbolo\n"
        result = corpus_service.import_csv(db, csv_content, default_lang="en")
        db.commit()
        assert result.imported == 1
        pair = db.query(CorpusPair).first()
        assert pair.source_language == "en"

    def test_import_csv_invalid_lang(self, db):
        csv_content = "source_language,source_text,bassa_text\nde,Hallo,Mbolo\n"
        result = corpus_service.import_csv(db, csv_content)
        assert result.imported == 0
        assert result.skipped == 1
        assert len(result.errors) == 1

    def test_import_csv_skip_empty_rows(self, db):
        csv_content = "source_language,source_text,bassa_text\nfr,,Mbolo\nfr,Bonjour,\nfr,Merci,A ngi nyu\n"
        result = corpus_service.import_csv(db, csv_content)
        db.commit()
        assert result.imported == 1
        assert result.skipped == 2

    def test_import_csv_missing_required_columns(self, db):
        csv_content = "source_language,source_text\nfr,Bonjour\n"
        result = corpus_service.import_csv(db, csv_content)
        assert result.imported == 0
        assert len(result.errors) == 1

    def test_import_csv_verified_flag(self, db):
        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\n"
        corpus_service.import_csv(db, csv_content, verified=False)
        db.commit()
        pair = db.query(CorpusPair).first()
        assert pair.is_verified is False

    def test_import_csv_is_verified_column_overrides(self, db):
        csv_content = "source_language,source_text,bassa_text,is_verified\nfr,Bonjour,Mbolo,true\nfr,Merci,A ngi nyu,false\n"
        corpus_service.import_csv(db, csv_content, verified=False)
        db.commit()
        pairs = db.query(CorpusPair).order_by(CorpusPair.id).all()
        assert pairs[0].is_verified is True
        assert pairs[1].is_verified is False

    def test_import_csv_with_optional_columns(self, db):
        csv_content = (
            "source_language,source_text,bassa_text,domain,source_reference\n"
            "fr,Notre Père,Tata wa biso,religion,Mt 6:9\n"
        )
        corpus_service.import_csv(db, csv_content)
        db.commit()
        pair = db.query(CorpusPair).first()
        assert pair.domain == "religion"
        assert pair.source_reference == "Mt 6:9"

    def test_import_csv_bytes_input(self, db):
        csv_bytes = b"source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\n"
        result = corpus_service.import_csv(db, csv_bytes)
        db.commit()
        assert result.imported == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests API corpus
# ─────────────────────────────────────────────────────────────────────────────

class TestCorpusAPI:

    def test_list_empty(self, client):
        resp = client.get("/api/corpus")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_create_requires_reviewer(self, client):
        # Anonyme
        resp = client.post("/api/corpus", json={
            "source_language": "fr",
            "source_text": "Bonjour",
            "bassa_text": "Mbolo",
        })
        assert resp.status_code == 401

        # Contributor simple
        client.post("/api/auth/register", json={
            "username": "contrib1",
            "email": "contrib1@test.com",
            "password": "pass123",
        })
        token_resp = client.post("/api/auth/login", json={"username": "contrib1", "password": "pass123"})
        token = token_resp.json()["access_token"]
        resp = client.post("/api/corpus", json={
            "source_language": "fr",
            "source_text": "Bonjour",
            "bassa_text": "Mbolo",
        }, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403

    def test_create_and_list(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.post("/api/corpus", json={
            "source_language": "fr",
            "source_text": "Bonjour",
            "bassa_text": "Mbolo",
            "is_verified": True,
        }, headers=headers)
        assert resp.status_code == 201
        pair = resp.json()
        assert pair["source_text"] == "Bonjour"
        assert pair["bassa_text"] == "Mbolo"

        list_resp = client.get("/api/corpus")
        assert list_resp.json()["total"] == 1

    def test_list_pagination(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        for i in range(5):
            client.post("/api/corpus", json={
                "source_language": "fr",
                "source_text": f"Phrase {i}",
                "bassa_text": f"Bassa {i}",
            }, headers=headers)

        resp = client.get("/api/corpus?page=1&size=3")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 3
        assert data["pages"] == 2

    def test_list_filter_lang(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/corpus", json={"source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo"}, headers=headers)
        client.post("/api/corpus", json={"source_language": "en", "source_text": "Hello", "bassa_text": "Mbolo"}, headers=headers)

        resp = client.get("/api/corpus?lang=fr")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["source_language"] == "fr"

    def test_list_search(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/corpus", json={"source_language": "fr", "source_text": "Bonjour monde", "bassa_text": "Mbolo"}, headers=headers)
        client.post("/api/corpus", json={"source_language": "fr", "source_text": "Au revoir", "bassa_text": "Bolo"}, headers=headers)

        resp = client.get("/api/corpus?search=Bonjour")
        assert resp.json()["total"] == 1

    def test_get_pair(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers=headers)
        pair_id = create.json()["id"]

        resp = client.get(f"/api/corpus/{pair_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == pair_id

    def test_get_pair_not_found(self, client):
        resp = client.get("/api/corpus/9999")
        assert resp.status_code == 404

    def test_update_pair(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        create = client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers=headers)
        pair_id = create.json()["id"]

        resp = client.put(f"/api/corpus/{pair_id}", json={"bassa_text": "Mbolo mis à jour"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["bassa_text"] == "Mbolo mis à jour"

    def test_delete_requires_admin(self, client):
        token_reviewer = _make_reviewer(client)
        headers_reviewer = {"Authorization": f"Bearer {token_reviewer}"}
        create = client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers=headers_reviewer)
        pair_id = create.json()["id"]

        resp = client.delete(f"/api/corpus/{pair_id}", headers=headers_reviewer)
        assert resp.status_code == 403

    def test_delete_as_admin(self, client):
        token_reviewer = _make_reviewer(client)
        token_admin = _make_admin(client)
        create = client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers={"Authorization": f"Bearer {token_reviewer}"})
        pair_id = create.json()["id"]

        resp = client.delete(f"/api/corpus/{pair_id}", headers={"Authorization": f"Bearer {token_admin}"})
        assert resp.status_code == 204

        resp = client.get(f"/api/corpus/{pair_id}")
        assert resp.status_code == 404

    def test_export_csv(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers=headers)

        resp = client.get("/api/corpus/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row
        assert "Bonjour" in lines[1]

    def test_export_csv_filter_lang(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/corpus", json={"source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo"}, headers=headers)
        client.post("/api/corpus", json={"source_language": "en", "source_text": "Hello", "bassa_text": "Mbolo"}, headers=headers)

        resp = client.get("/api/corpus/export?lang=fr")
        lines = resp.text.strip().split("\n")
        assert len(lines) == 2  # header + 1

    def test_stats(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo", "is_verified": True,
        }, headers=headers)
        client.post("/api/corpus", json={
            "source_language": "en", "source_text": "Hello", "bassa_text": "Mbolo", "is_verified": False,
        }, headers=headers)

        resp = client.get("/api/corpus/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["verified"] == 1
        assert data["fr"] == 1
        assert data["en"] == 1

    def test_import_csv_endpoint(self, client):
        token = _make_admin(client)
        headers = {"Authorization": f"Bearer {token}"}

        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\nfr,Merci,A ngi nyu\n"
        resp = client.post(
            "/api/corpus/import",
            files={"file": ("corpus.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert data["skipped"] == 0

        list_resp = client.get("/api/corpus")
        assert list_resp.json()["total"] == 2

    def test_import_csv_requires_admin(self, client):
        token = _make_reviewer(client)
        headers = {"Authorization": f"Bearer {token}"}
        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo\n"
        resp = client.post(
            "/api/corpus/import",
            files={"file": ("corpus.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_import_csv_bad_extension(self, client):
        token = _make_admin(client)
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.post(
            "/api/corpus/import",
            files={"file": ("corpus.txt", io.BytesIO(b"data"), "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_import_csv_skip_duplicates(self, client):
        token_reviewer = _make_reviewer(client)
        token_admin = _make_admin(client)
        # Créer une paire d'abord
        client.post("/api/corpus", json={
            "source_language": "fr", "source_text": "Bonjour", "bassa_text": "Mbolo",
        }, headers={"Authorization": f"Bearer {token_reviewer}"})

        # Importer avec le même source_text
        csv_content = "source_language,source_text,bassa_text\nfr,Bonjour,Mbolo v2\nfr,Merci,A ngi nyu\n"
        resp = client.post(
            "/api/corpus/import",
            files={"file": ("corpus.csv", io.BytesIO(csv_content.encode()), "text/csv")},
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        data = resp.json()
        assert data["imported"] == 1
        assert data["skipped"] == 1
