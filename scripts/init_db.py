"""Initialize the database: create tables, seed dictionary data, create admin user."""
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from backend.config import settings
from backend.database import engine, Base, SessionLocal
from backend.models.user import User, UserRole
from backend.models.dictionary import DictionaryEntry, DictionaryExample
from backend.models.corpus import CorpusPair
from backend.models.contribution import Contribution
from backend.models.grammar import GrammaticalRule
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SEED_FILE = Path(__file__).resolve().parent.parent / "backend" / "seed" / "dictionary_seed.json"


def create_database():
    """Create the MySQL database if it doesn't exist."""
    db_url = settings.DATABASE_URL
    if "mysql" in db_url:
        # Extract database name from URL
        db_name = db_url.rsplit("/", 1)[-1].split("?")[0]
        base_url = db_url.rsplit("/", 1)[0]
        temp_engine = __import__("sqlalchemy").create_engine(base_url)
        with temp_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
            conn.commit()
        temp_engine.dispose()
        print(f"Database '{db_name}' ensured.")


def create_tables():
    """Create all tables."""
    Base.metadata.create_all(bind=engine)
    print("Tables created.")


def seed_admin():
    """Create default admin user."""
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == "admin").first()
        if existing:
            print("Admin user already exists, skipping.")
            return
        admin = User(
            username="admin",
            email="admin@bassatranslator.local",
            hashed_password=pwd_context.hash("admin123"),
            role=UserRole.admin,
        )
        db.add(admin)
        db.commit()
        print("Admin user created (admin / admin123).")
    finally:
        db.close()


def seed_dictionary():
    """Seed dictionary from JSON file."""
    db = SessionLocal()
    try:
        count = db.query(DictionaryEntry).count()
        if count > 0:
            print(f"Dictionary already has {count} entries, skipping seed.")
            return

        with open(SEED_FILE, "r", encoding="utf-8") as f:
            entries = json.load(f)

        for item in entries:
            examples_data = item.pop("examples", [])
            entry = DictionaryEntry(
                source_language=item["source_language"],
                source_word=item["source_word"],
                bassa_word=item["bassa_word"],
                phonetic=item.get("phonetic"),
                category=item.get("category"),
                gender=item.get("gender"),
                plural_form=item.get("plural_form"),
                notes=item.get("notes"),
                is_verified=True,
            )
            db.add(entry)
            db.flush()
            for ex in examples_data:
                example = DictionaryExample(
                    entry_id=entry.id,
                    source_sentence=ex["source_sentence"],
                    bassa_sentence=ex["bassa_sentence"],
                )
                db.add(example)

        db.commit()
        print(f"Seeded {len(entries)} dictionary entries.")
    finally:
        db.close()


def seed_grammar_rules():
    """Seed basic grammatical transformation rules."""
    db = SessionLocal()
    try:
        count = db.query(GrammaticalRule).count()
        if count > 0:
            print(f"Grammar rules already exist ({count}), skipping.")
            return

        rules = [
            GrammaticalRule(
                rule_name="FR subject-verb order",
                source_language="fr",
                pattern="PRON VERB",
                transformation="PRON VERB",
                priority=10,
                is_active=True,
            ),
            GrammaticalRule(
                rule_name="FR negation ne...pas removal",
                source_language="fr",
                pattern="ne VERB pas",
                transformation="VERB ga",
                priority=20,
                is_active=True,
            ),
            GrammaticalRule(
                rule_name="EN subject-verb order",
                source_language="en",
                pattern="PRON VERB",
                transformation="PRON VERB",
                priority=10,
                is_active=True,
            ),
        ]
        db.add_all(rules)
        db.commit()
        print(f"Seeded {len(rules)} grammar rules.")
    finally:
        db.close()


if __name__ == "__main__":
    print("=== BassaAI Translator - Database Initialization ===")
    create_database()
    create_tables()
    seed_admin()
    seed_dictionary()
    seed_grammar_rules()
    print("=== Done! ===")
