from backend.models.user import User, UserRole
from backend.services.auth_service import hash_password, create_access_token


def _create_admin(db):
    user = User(username="admin", email="admin@test.com", hashed_password=hash_password("admin"), role=UserRole.admin)
    db.add(user)
    db.commit()
    db.refresh(user)
    return create_access_token({"sub": str(user.id), "role": user.role.value})


def test_list_dictionary_empty(client):
    resp = client.get("/api/dictionary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_entry_requires_auth(client):
    resp = client.post("/api/dictionary", json={
        "source_word": "test", "bassa_word": "test"
    })
    assert resp.status_code == 401


def test_crud_dictionary(client, db):
    token = _create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    resp = client.post("/api/dictionary", json={
        "source_language": "fr",
        "source_word": "maison",
        "bassa_word": "ndap",
        "category": "noun"
    }, headers=headers)
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    # Read
    resp = client.get(f"/api/dictionary/{entry_id}")
    assert resp.status_code == 200
    assert resp.json()["source_word"] == "maison"

    # Update
    resp = client.put(f"/api/dictionary/{entry_id}", json={
        "phonetic": "ndap"
    }, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["phonetic"] == "ndap"

    # Delete
    resp = client.delete(f"/api/dictionary/{entry_id}", headers=headers)
    assert resp.status_code == 204

    # Verify deleted
    resp = client.get(f"/api/dictionary/{entry_id}")
    assert resp.status_code == 404


def test_search_dictionary(client, db):
    token = _create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    client.post("/api/dictionary", json={
        "source_word": "eau", "bassa_word": "mandap", "source_language": "fr"
    }, headers=headers)
    client.post("/api/dictionary", json={
        "source_word": "water", "bassa_word": "mandap", "source_language": "en"
    }, headers=headers)

    resp = client.get("/api/dictionary?search=eau")
    assert resp.json()["total"] == 1

    resp = client.get("/api/dictionary?lang=en")
    assert resp.json()["total"] == 1


def test_search_is_tonal_tolerant(client, db):
    token = _create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    # Insert a Basaa word with tonal marks
    client.post("/api/dictionary", json={
        "source_word": "boire", "bassa_word": "nyó", "source_language": "fr"
    }, headers=headers)

    # User searches without the accent → should still find the entry
    resp = client.get("/api/dictionary?search=nyo")
    data = resp.json()
    assert data["total"] >= 1
    assert any(item["bassa_word"] == "nyó" for item in data["items"])

    # User searches WITH the accent → still finds it
    resp = client.get("/api/dictionary?search=nyó")
    assert resp.json()["total"] >= 1


def test_create_entry_populates_normalized(client, db):
    from backend.models.dictionary import DictionaryEntry

    token = _create_admin(db)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/api/dictionary", json={
        "source_word": "lune", "bassa_word": "sôñ", "source_language": "fr"
    }, headers=headers)
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    # The before_insert listener should have populated bassa_word_normalized
    entry = db.query(DictionaryEntry).filter(DictionaryEntry.id == entry_id).first()
    assert entry.bassa_word_normalized == "soñ"
