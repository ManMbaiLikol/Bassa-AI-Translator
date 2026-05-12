"""Quick smoke test for Bassa->FR reverse translation (no server needed)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.engine.dictionary_engine import DictionaryEngine
from backend.database import SessionLocal
from backend.models.corpus import CorpusPair


def main():
    print("Loading DictionaryEngine (with corpus index)...")
    eng = DictionaryEngine()
    print(f"  reverse dict entries: {len(eng._reverse)}")
    print(f"  reverse multi entries: {len(eng._reverse_multi)}")
    print(f"  corpus pairs indexed:  {len(eng._corpus_pairs)}")
    print(f"  corpus tokens indexed: {len(eng._corpus_bassa_index)}")
    print()

    # ---- Test 1: single Bassa word (should hit _reverse) ----
    # Pull a few known single-word entries from the reverse cache
    samples_dict = list(eng._reverse.items())[:3]
    print("=== TEST 1 — Single-word Bassa->FR (dict reverse) ===")
    for bas, fr in samples_dict:
        result = eng.translate(bas, "bas")
        print(f"  {bas!r} -> {result.translated_text!r}  "
              f"[conf={result.confidence} engine={result.engine}]")
    print()

    # ---- Test 2: full Bible verse (should hit corpus search with F1~1.0) ----
    print("=== TEST 2 — Full Bible verse Bassa->FR (corpus exact) ===")
    db = SessionLocal()
    verses = db.query(CorpusPair).filter(CorpusPair.source_language == "fr").limit(3).all()
    for v in verses:
        result = eng.translate(v.bassa_text, "bas")
        print(f"  Bassa input:  {v.bassa_text[:70]}...")
        print(f"  Expected FR:  {v.source_text[:70]}...")
        print(f"  Got FR:       {result.translated_text[:70]}...")
        print(f"  conf={result.confidence} engine={result.engine} "
              f"warnings={result.warnings}")
        print()

    # ---- Test 3: partial Bassa phrase (should hit corpus search with lower F1) ----
    print("=== TEST 3 — Partial Bassa phrase Bassa->FR (corpus approx) ===")
    if verses:
        # Take ~half of the first verse and see what we get
        partial = " ".join(verses[0].bassa_text.split()[:6])
        result = eng.translate(partial, "bas")
        print(f"  Partial Bassa: {partial}")
        print(f"  Got FR:        {result.translated_text[:90]}")
        print(f"  conf={result.confidence} engine={result.engine} warnings={result.warnings}")
    print()

    # ---- Test 4: gibberish Bassa (should fall through to token fallback) ----
    print("=== TEST 4 — Unknown Bassa (token fallback) ===")
    result = eng.translate("xyzqq abcdef", "bas")
    print(f"  Input: 'xyzqq abcdef'")
    print(f"  translated_text: {result.translated_text!r}")
    print(f"  conf={result.confidence} warnings={result.warnings}")

    db.close()


if __name__ == "__main__":
    main()
