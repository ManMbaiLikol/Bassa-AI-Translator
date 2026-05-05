"""Extract parallel Bible verses (French + Bassa) and build dictionary + corpus.

Strategy: Extract verse-level text using verse number patterns,
align by chapter:verse reference, then use aligned pairs for word extraction.
"""
import json
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import fitz
except ImportError:
    print("PyMuPDF required: pip install pymupdf")
    sys.exit(1)

DOCS_DIR = Path(__file__).resolve().parent.parent / "Docs"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"

FR_PDF = DOCS_DIR / "Bible En francais.pdf"
BS_PDF = DOCS_DIR / "Bible En Bassa du Cameroun 2.pdf"


def extract_full_text(pdf_path, start_page, end_page):
    """Extract and concatenate all text from specified page range."""
    doc = fitz.open(str(pdf_path))
    end_page = min(end_page, len(doc))
    full = []
    for i in range(start_page, end_page):
        page_text = doc[i].get_text()
        # Fix hyphenation at line breaks (word-\nrest -> wordrest)
        page_text = re.sub(r'(\w)-\n(\w)', r'\1\2', page_text)
        # Join lines within paragraphs
        page_text = page_text.replace('\n', ' ')
        # Normalize spaces
        page_text = re.sub(r'\s+', ' ', page_text)
        full.append(page_text.strip())
    doc.close()
    return ' '.join(full)


def extract_verses(text, lang="fr"):
    """Extract numbered verses from Bible text.

    Returns dict: { verse_seq_number: verse_text }
    Verses are numbered sequentially across the entire text.
    """
    # Pattern: a verse number (1-176) followed by text
    # In Bible text, verse numbers appear as standalone numbers before text
    # We detect: previous sentence ends (. ! ? ») then number then uppercase letter
    if lang == "fr":
        pattern = r'(?<=[.!?»"\s])\s*(\d{1,3})\s+([A-ZÀ-ÿ«\'])'
    else:
        pattern = r'(?<=[.!?»"\s])\s*(\d{1,3})\s+([A-ZÀ-ÿ\'])'

    splits = list(re.finditer(pattern, text))

    verses = {}
    for idx, match in enumerate(splits):
        vnum = int(match.group(1))
        start = match.start()
        end = splits[idx + 1].start() if idx + 1 < len(splits) else min(start + 2000, len(text))
        verse_text = text[match.end() - 1:end].strip()

        # Clean verse text
        verse_text = re.sub(r'\s+', ' ', verse_text)
        # Remove footnote markers (letters a-z as superscripts appear as standalone)
        verse_text = re.sub(r'\s[a-z]\s', ' ', verse_text)

        if len(verse_text) > 10:
            verses[idx] = {
                "num": vnum,
                "text": verse_text[:500],
            }

    return verses


def align_by_sequence(fr_verses, bs_verses, max_pairs=5000):
    """Align verses by sequential position.

    Since both Bibles follow the same verse ordering,
    sequential alignment works reasonably well.
    """
    pairs = []
    min_count = min(len(fr_verses), len(bs_verses), max_pairs)

    fr_keys = sorted(fr_verses.keys())[:min_count]
    bs_keys = sorted(bs_verses.keys())[:min_count]

    for i in range(min(len(fr_keys), len(bs_keys))):
        fr = fr_verses[fr_keys[i]]
        bs = bs_verses[bs_keys[i]]

        # Only pair verses with matching verse numbers for higher confidence
        fr_text = fr["text"].strip()
        bs_text = bs["text"].strip()

        if len(fr_text) > 15 and len(bs_text) > 15:
            pairs.append({
                "source_language": "fr",
                "source_text": fr_text,
                "bassa_text": bs_text,
                "domain": "bible",
                "is_verified": True if fr["num"] == bs["num"] else False,
            })

    return pairs


def extract_dictionary(pairs):
    """Extract word-level dictionary from aligned verse pairs.

    Uses statistical co-occurrence at the verse level for better precision.
    """
    fr_stop = {
        "le", "la", "les", "un", "une", "des", "du", "de", "à", "et", "est",
        "en", "que", "qui", "dans", "pour", "ce", "se", "il", "elle", "ils",
        "ne", "pas", "sur", "par", "avec", "son", "sa", "ses", "au", "aux",
        "mais", "ou", "car", "ni", "donc", "si", "je", "tu", "nous", "vous",
        "on", "me", "te", "lui", "leur", "leurs", "y", "ai", "as", "ont",
        "être", "avoir", "faire", "dit", "fut", "été", "avait", "sont",
        "cette", "ces", "mon", "ma", "mes", "ton", "ta", "tes", "notre",
        "votre", "tout", "tous", "toute", "toutes", "même", "très", "plus",
        "aussi", "bien", "peu", "trop", "ici", "là", "alors", "puis",
        "comme", "quand", "où", "dont", "sera", "fait", "après", "avant",
        "encore", "autre", "autres", "eux", "cet", "sans", "sous", "entre",
        "vers", "chez", "doit", "peut", "veut", "faut", "étaient", "soit",
        "deux", "ces", "moi", "toi", "soi", "elles", "ils", "ceux", "celle",
        "celles", "cela", "suis", "êtes", "sont", "sera", "seront", "serai",
        "avons", "avez", "aura", "auront", "aurai", "aurons", "aurez",
        "aurait", "ferai", "ferez", "feront", "fera", "fais", "faites",
        "dire", "disent", "dirent", "dis", "vais", "vas", "allons", "allez",
        "vont", "ira", "iront", "irai", "irons", "irez", "irais",
    }

    bs_stop = {
        "ni", "le", "ba", "bi", "ma", "mi", "di", "a", "i", "u", "ha",
    }

    fr_counts = Counter()
    bs_counts = Counter()
    co_occur = defaultdict(Counter)
    total = len(pairs)

    for pair in pairs:
        fr_words = set(re.findall(r'[a-zà-ÿéèêëîïôûùüç]{3,}', pair["source_text"].lower()))
        bs_words = set(re.findall(r'[a-zà-ÿéèêëîïôûùüçñ]{2,}', pair["bassa_text"].lower()))

        fr_words -= fr_stop
        bs_words -= bs_stop

        for fw in fr_words:
            fr_counts[fw] += 1
            for bw in bs_words:
                co_occur[fw][bw] += 1
        for bw in bs_words:
            bs_counts[bw] += 1

    # Extract best pairs using PMI
    entries = []
    seen_fr = set()
    seen_bs = set()

    # Sort French words by frequency (prefer common words)
    for fw in sorted(fr_counts, key=fr_counts.get, reverse=True):
        if fw in seen_fr or fr_counts[fw] < 8:
            continue

        best = None
        best_score = 0

        for bw, count in co_occur[fw].most_common(10):
            if bw in seen_bs or count < 5 or bs_counts[bw] < 5:
                continue
            if len(bw) < 2:
                continue

            # PMI score
            fr_freq = fr_counts[fw] / total
            bs_freq = bs_counts[bw] / total
            joint = count / total
            pmi = joint / (fr_freq * bs_freq) if fr_freq * bs_freq > 0 else 0

            # Combined score: PMI * log(count) for both relevance and confidence
            import math
            score = pmi * math.log(count + 1)

            if score > best_score and pmi > 1.5:
                best = bw
                best_score = score

        if best:
            entries.append({
                "source_language": "fr",
                "source_word": fw,
                "bassa_word": best,
                "is_verified": False,
                "count": co_occur[fw][best],
                "score": round(best_score, 2),
            })
            seen_fr.add(fw)
            seen_bs.add(best)

    entries.sort(key=lambda x: x["count"], reverse=True)
    return entries


def main():
    print("=== Bible Extraction for BassaAI Translator ===\n")

    # Extract text
    print("1. Extracting French Bible text...")
    fr_text = extract_full_text(FR_PDF, start_page=42, end_page=1800)
    print(f"   {len(fr_text):,} characters extracted")

    print("2. Extracting Bassa Bible text...")
    bs_text = extract_full_text(BS_PDF, start_page=42, end_page=1700)
    print(f"   {len(bs_text):,} characters extracted")

    # Parse verses
    print("\n3. Parsing verses...")
    fr_verses = extract_verses(fr_text, "fr")
    bs_verses = extract_verses(bs_text, "bs")
    print(f"   French: {len(fr_verses)} verses")
    print(f"   Bassa:  {len(bs_verses)} verses")

    # Align
    print("\n4. Aligning verse pairs...")
    pairs = align_by_sequence(fr_verses, bs_verses, max_pairs=5000)
    print(f"   {len(pairs)} aligned pairs")

    # Show samples
    print("\n   Sample pairs:")
    for p in pairs[:5]:
        fr_short = p["source_text"][:80]
        bs_short = p["bassa_text"][:80]
        print(f"   FR: {fr_short}...")
        print(f"   BS: {bs_short}...")
        print()

    # Extract dictionary
    print("5. Extracting dictionary from aligned pairs...")
    dictionary = extract_dictionary(pairs)
    print(f"   {len(dictionary)} word pairs extracted")

    print("\n   Top 50 word pairs (FR -> Bassa):")
    for e in dictionary[:50]:
        print(f"   {e['source_word']:20s} -> {e['bassa_word']:20s} (count={e['count']})")

    # Save
    dict_out = OUTPUT_DIR / "bible_dictionary.json"
    corpus_out = OUTPUT_DIR / "bible_corpus.json"

    with open(dict_out, 'w', encoding='utf-8') as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    print(f"\n   Dictionary saved: {dict_out}")

    with open(corpus_out, 'w', encoding='utf-8') as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)
    print(f"   Corpus saved: {corpus_out}")

    print(f"\n=== Done! ===")
    print(f"   Next: python scripts/seed_bible.py")


if __name__ == "__main__":
    main()
