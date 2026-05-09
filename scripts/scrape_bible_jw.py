"""Scrape parallel Bible verses (French + Bassa) from JW.org.

Usage:
    python scripts/scrape_bible_jw.py [--books ALL|NT|OT] [--delay 1.5] [--resume]

Fetches the New World Translation in French and Bassa, aligns verses by number,
saves corpus to backend/seed/bible_jw_corpus.json.
Then run: python scripts/seed_bible_jw.py
"""
import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

# Force UTF-8 output (safe on both console and file redirect)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE_BASSA = "https://www.jw.org/bas/bikaat/bibel/nwt/bikaat/"
BASE_FR    = "https://www.jw.org/fr/biblioth%C3%A8que/bible/bible-d-etude/livres/"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"
CHECKPOINT = None  # Set dynamically from --out in main()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

# (bassa_slug, french_slug, chapters, testament)
BOOKS = [
    # Old Testament
    ("Bib%C3%B4dle",                 "Gen%C3%A8se",              50, "OT"),
    ("manyodi",                       "Exode",                    40, "OT"),
    ("L%C3%B4k-L%C3%A9vi",           "L%C3%A9vitique",           27, "OT"),
    ("%C3%91a%C3%B1ga-b%C3%B4t",     "Nombres",                  36, "OT"),
    ("Ndiimba-Mb%C3%A9n",            "Deut%C3%A9ronome",         34, "OT"),
    ("Y%C3%B4sua",                   "Josu%C3%A9",               24, "OT"),
    ("Bak%C3%A9%C3%A9s",             "Juges",                    21, "OT"),
    ("ruth",                          "Ruth",                      4, "OT"),
    ("1-samuel",                      "1-Samuel",                 31, "OT"),
    ("2-samuel",                      "2-Samuel",                 24, "OT"),
    ("1-Biki%C3%B1e",                "1-Rois",                   22, "OT"),
    ("2-Biki%C3%B1e",                "2-Rois",                   25, "OT"),
    ("1-Mi%C3%B1a%C3%B1",           "1-Chroniques",             29, "OT"),
    ("2-Mi%C3%B1a%C3%B1",           "2-Chroniques",             36, "OT"),
    ("%C3%89sra",                    "Esdras",                   10, "OT"),
    ("N%C3%A9h%C3%A9mia",           "N%C3%A9h%C3%A9mie",        13, "OT"),
    ("%C3%89ster",                   "Esther",                   10, "OT"),
    ("Hi%C3%B4b",                    "Job",                      42, "OT"),
    ("Tj%C3%A9mbi",                  "Psaumes",                 150, "OT"),
    ("Bing%C3%A9ng%C3%A9n",          "Proverbes",                31, "OT"),
    ("%C3%91a%C3%B1al",              "Eccl%C3%A9siaste",         12, "OT"),
    ("Hi%C3%A9mbi-hi-Sal%C3%B4m%C3%B4", "Cantique-de-Salomon",  8, "OT"),
    ("Y%C3%A9saya",                  "%C3%89sa%C3%AFe",          66, "OT"),
    ("Y%C3%A9r%C3%A9mia",           "J%C3%A9r%C3%A9mie",        52, "OT"),
    ("Minl%C3%A9nd-mi-Y%C3%A9r%C3%A9mia", "Lamentations",        5, "OT"),
    ("%C3%89z%C3%A9kiel",           "%C3%89z%C3%A9chiel",        48, "OT"),
    ("daniel",                        "Daniel",                   12, "OT"),
    ("H%C3%B4s%C3%A9a",             "Os%C3%A9e",                14, "OT"),
    ("Y%C3%B4el",                    "Jo%C3%ABl",                 3, "OT"),
    ("Am%C3%B4s",                    "Amos",                      9, "OT"),
    ("%C3%94badia",                  "Abdias",                    1, "OT"),
    ("Y%C3%B4na",                    "Jonas",                     4, "OT"),
    ("mika",                          "Mich%C3%A9e",               7, "OT"),
    ("nahum",                         "Nahoum",                    3, "OT"),
    ("habakuk",                       "Habacuc",                   3, "OT"),
    ("S%C3%B4f%C3%B4nia",           "Sophonie",                   3, "OT"),
    ("hagai",                         "Agg%C3%A9e",                2, "OT"),
    ("sakaria",                       "Zacharie",                 14, "OT"),
    ("malaki",                        "Malachie",                  4, "OT"),
    # New Testament
    ("Mat%C3%A9%C3%B4",             "Matthieu",                  28, "NT"),
    ("Mark%C3%B4",                   "Marc",                     16, "NT"),
    ("lukas",                         "Luc",                      24, "NT"),
    ("Y%C3%B4hanes",                 "Jean",                      21, "NT"),
    ("Minson-mi-ba%C3%B4ma",         "Actes",                    28, "NT"),
    ("R%C3%B4ma",                    "Romains",                   16, "NT"),
    ("1-Korint%C3%B4",              "1-Corinthiens",             16, "NT"),
    ("2-Korint%C3%B4",              "2-Corinthiens",             13, "NT"),
    ("galatia",                       "Galates",                   6, "NT"),
    ("%C3%89f%C3%A9s%C3%B4",        "%C3%89ph%C3%A9siens",        6, "NT"),
    ("filipi",                        "Philippiens",               4, "NT"),
    ("K%C3%B4l%C3%B4s%C3%A9",       "Colossiens",                 4, "NT"),
    ("1-T%C3%A9sal%C3%B4nika",      "1-Thessaloniciens",          5, "NT"),
    ("2-T%C3%A9sal%C3%B4nika",      "2-Thessaloniciens",          3, "NT"),
    ("1-Tim%C3%B4t%C3%A9%C3%B4",   "1-Timoth%C3%A9e",            6, "NT"),
    ("2-Tim%C3%B4t%C3%A9%C3%B4",   "2-Timoth%C3%A9e",            4, "NT"),
    ("Tit%C3%B4",                   "Tite",                        3, "NT"),
    ("Fil%C3%A9m%C3%B4n",           "Phil%C3%A9mon",               1, "NT"),
    ("L%C3%B4k-H%C3%A9ber",         "H%C3%A9breux",               13, "NT"),
    ("Yak%C3%B4b%C3%B4",            "Jacques",                     5, "NT"),
    ("1-P%C3%A9tr%C3%B4",           "1-Pierre",                    5, "NT"),
    ("2-P%C3%A9tr%C3%B4",           "2-Pierre",                    3, "NT"),
    ("1-Y%C3%B4hanes",              "1-Jean",                      5, "NT"),
    ("2-Y%C3%B4hanes",              "2-Jean",                      1, "NT"),
    ("3-Y%C3%B4hanes",              "3-Jean",                      1, "NT"),
    ("yuda",                          "Jude",                       1, "NT"),
    ("masoola",                       "R%C3%A9v%C3%A9lation",      22, "NT"),
]


def fetch_html(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                return r.text
            if r.status_code == 404:
                return None
            print(f"    HTTP {r.status_code} for {url}")
        except requests.RequestException as e:
            print(f"    Error: {e}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return None


def parse_verses(html: str, lang: str) -> dict[int, str]:
    """Extract {verse_number: text} from a JW.org Bible chapter page.

    JW.org structure:
      - <sup class="verseNum"><a data-anchor="#vBBBCCCVVV">N </a></sup>
      - Each verse (except v1) is wrapped in <span class="style-l">
      - Verse 1 text precedes the first style-l span
    """
    soup = BeautifulSoup(html, "html.parser")
    verses: dict[int, str] = {}

    # Primary strategy: sup.verseNum elements
    verse_sups = soup.find_all("sup", class_="verseNum")
    if verse_sups:
        for sup in verse_sups:
            # Extract verse number from anchor text or data-anchor
            a = sup.find("a")
            if not a:
                continue
            num_text = a.get_text(strip=True).replace("\xa0", "").replace(" ", "").strip()
            if not num_text.isdigit():
                # Try data-anchor: "#v40001002" -> last 3 digits
                anchor = a.get("data-anchor", "")
                m = re.search(r"(\d{3})$", anchor)
                if m:
                    num_text = str(int(m.group(1)))
                else:
                    continue
            vnum = int(num_text)

            # The verse text is in the parent span (style-b for narrative, style-l for poetry)
            parent = sup.parent or sup.find_parent(["span", "p", "li"])
            if not parent:
                continue
            # Clone and remove all sup elements to get clean text
            p_copy = BeautifulSoup(str(parent), "html.parser")
            for s in p_copy.find_all("sup"):
                s.decompose()
            # Remove footnote symbols (* + etc.)
            text = p_copy.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 5:
                verses[vnum] = text

        # Verse 1: find text before the first style-l span in the reading div
        if 1 not in verses:
            reading = soup.find("div", class_=re.compile(r"BibleReadingPage|reading"))
            if not reading:
                reading = soup.find("div", id="regionMain")
            if reading:
                first_style_l = reading.find("span", class_="style-l")
                if first_style_l:
                    # Get the paragraph containing the first verse
                    para = first_style_l.find_parent(["p", "div", "section"])
                    if para:
                        # Collect text nodes before the first style-l
                        text_parts = []
                        for child in para.children:
                            if child == first_style_l or (hasattr(child, "find") and child.find("span", class_="style-l")):
                                break
                            if hasattr(child, "get_text"):
                                t = child.get_text(" ", strip=True)
                            else:
                                t = str(child).strip()
                            if t:
                                text_parts.append(t)
                        v1 = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
                        # Remove leading verse number if present (e.g. "1 Text...")
                        v1 = re.sub(r"^\d+\s+", "", v1).strip()
                        if len(v1) > 10:
                            verses[1] = v1

    # Fallback: regex on plain text
    if len(verses) < 3:
        verses = {}
        # Get main content area only (avoid navigation noise)
        reading = soup.find("div", class_=re.compile(r"BibleReadingPage|reading"))
        text_content = reading.get_text(" ") if reading else soup.get_text(" ")
        text_content = re.sub(r"[*+]", "", text_content)
        # Split on verse number patterns: standalone digit(s) at word boundary
        parts = re.split(r"(?<!\w)(\d{1,3})(?=\s+[A-ZÀ-ÿa-z])", text_content)
        i = 0
        while i < len(parts) - 2:
            vnum_str = parts[i + 1]
            verse_text = parts[i + 2]
            if vnum_str.isdigit():
                vnum = int(vnum_str)
                if 1 <= vnum <= 176 and len(verse_text) > 10:
                    verses[vnum] = re.sub(r"\s+", " ", verse_text[:400]).strip()
            i += 2

    return verses


def clean_verse(text: str) -> str:
    """Remove footnote markers and normalize whitespace."""
    text = re.sub(r"\+\s*", "", text)          # footnote + markers
    text = re.sub(r"\*\s*", "", text)          # asterisks
    text = re.sub(r"\[\d+\]", "", text)        # [1] [2] markers
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def scrape_chapter(bassa_slug: str, fr_slug: str, chap: int, delay: float) -> list[dict]:
    """Fetch and align one chapter in both languages."""
    url_bas = f"{BASE_BASSA}{bassa_slug}/{chap}/"
    url_fr  = f"{BASE_FR}{fr_slug}/{chap}/"

    html_bas = fetch_html(url_bas)
    time.sleep(delay / 2)
    html_fr  = fetch_html(url_fr)
    time.sleep(delay / 2)

    if not html_bas or not html_fr:
        return []

    verses_bas = parse_verses(html_bas, "bas")
    verses_fr  = parse_verses(html_fr, "fr")

    pairs = []
    for vnum in sorted(set(verses_bas) & set(verses_fr)):
        fr_text  = clean_verse(verses_fr[vnum])
        bas_text = clean_verse(verses_bas[vnum])
        if len(fr_text) > 10 and len(bas_text) > 10:
            pairs.append({
                "source_language": "fr",
                "source_text":  fr_text[:600],
                "bassa_text":   bas_text[:600],
                "domain":       "bible",
                "source_reference": f"v{vnum}",
                "is_verified":  True,
            })
    return pairs


def extract_dictionary(corpus: list[dict]) -> list[dict]:
    """Statistical word alignment (IBM Model 1-style) using PMI."""
    fr_stop = {
        "le","la","les","un","une","des","du","de","à","et","est","en","que","qui",
        "dans","pour","ce","se","il","elle","ils","ne","pas","sur","par","avec",
        "son","sa","ses","au","aux","mais","ou","car","ni","donc","si","je","tu",
        "nous","vous","on","me","te","lui","leur","leurs","y","ai","as","ont",
        "être","avoir","faire","dit","fut","été","avait","sont","cette","ces",
        "mon","ma","mes","ton","ta","tes","notre","votre","tout","tous","toute",
        "toutes","même","très","plus","aussi","bien","peu","trop","ici","là",
        "alors","puis","comme","quand","où","dont","sera","fait","après","avant",
        "encore","autre","autres","eux","cet","sans","sous","entre","vers","chez",
        "doit","peut","veut","faut","étaient","soit","deux","cela","suis","êtes",
    }
    bs_stop = {"ni","le","ba","bi","ma","mi","di","a","i","u","ha","bo","mu","hi","ke"}

    fr_counts: Counter = Counter()
    bs_counts: Counter = Counter()
    co_occur: defaultdict = defaultdict(Counter)
    total = len(corpus)

    for pair in corpus:
        fr_words = {w for w in re.findall(r"[a-zà-ÿéèêëîïôûùüç]{3,}", pair["source_text"].lower()) if w not in fr_stop}
        bs_words = {w for w in re.findall(r"[a-zà-ÿéèêëîïôûùüçñô]{2,}", pair["bassa_text"].lower()) if w not in bs_stop}
        for fw in fr_words:
            fr_counts[fw] += 1
            for bw in bs_words:
                co_occur[fw][bw] += 1
        for bw in bs_words:
            bs_counts[bw] += 1

    entries = []
    seen_fr: set = set()
    seen_bs: set = set()
    min_count = max(3, total // 200)

    for fw in sorted(fr_counts, key=fr_counts.get, reverse=True):
        if fw in seen_fr or fr_counts[fw] < min_count:
            continue
        best = None
        best_score = 0.0
        for bw, cnt in co_occur[fw].most_common(8):
            if bw in seen_bs or cnt < 3 or bs_counts[bw] < 3 or len(bw) < 2:
                continue
            fr_freq = fr_counts[fw] / total
            bs_freq = bs_counts[bw] / total
            joint   = cnt / total
            pmi     = joint / (fr_freq * bs_freq) if fr_freq * bs_freq > 0 else 0
            score   = pmi * math.log(cnt + 1)
            if score > best_score and pmi > 1.2:
                best, best_score = bw, score
        if best:
            entries.append({
                "source_language": "fr",
                "source_word":     fw,
                "bassa_word":      best,
                "is_verified":     False,
                "count":           co_occur[fw][best],
                "score":           round(best_score, 2),
            })
            seen_fr.add(fw)
            seen_bs.add(best)

    return sorted(entries, key=lambda x: x["count"], reverse=True)


def load_checkpoint(ckpt: Path) -> dict:
    if ckpt.exists():
        with open(ckpt, encoding="utf-8") as f:
            return json.load(f)
    return {"done": [], "corpus": []}


def save_checkpoint(state: dict, ckpt: Path):
    with open(ckpt, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--books", choices=["ALL", "NT", "OT"], default="ALL")
    parser.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--out", default=str(OUTPUT_DIR / "bible_jw_corpus.json"))
    args = parser.parse_args()

    books = [b for b in BOOKS if args.books == "ALL" or b[3] == args.books]
    total_chapters = sum(b[2] for b in books)
    print(f"=== JW.org Bible Scraper ===")
    print(f"  Books: {args.books} ({len(books)} livres, {total_chapters} chapitres)")
    print(f"  Delay: {args.delay}s  |  Est. time: {total_chapters * args.delay * 2 / 60:.0f} min\n")

    # Checkpoint derived from output file name
    out_path = Path(args.out)
    ckpt = out_path.with_suffix(".checkpoint.json")

    state = load_checkpoint(ckpt) if args.resume else {"done": [], "corpus": []}
    done_set = set(state["done"])
    corpus: list[dict] = state["corpus"]

    for book in books:
        bas_slug, fr_slug, chapters, _ = book
        for chap in range(1, chapters + 1):
            key = f"{bas_slug}/{chap}"
            if key in done_set:
                continue

            pairs = scrape_chapter(bas_slug, fr_slug, chap, args.delay)
            corpus.extend(pairs)
            done_set.add(key)
            state["done"] = list(done_set)
            state["corpus"] = corpus
            save_checkpoint(state, ckpt)

            status = f"  {bas_slug[:20]:20s} ch.{chap:3d} -> {len(pairs):3d} paires | total={len(corpus)}"
            print(status, flush=True)

    # Save final corpus
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(corpus, f, ensure_ascii=False, indent=2)
    print(f"\n  Corpus sauvegardé: {out_path} ({len(corpus)} paires)")

    # Extract dictionary
    print("\n  Extraction du vocabulaire...")
    dictionary = extract_dictionary(corpus)
    dict_path = OUTPUT_DIR / "bible_jw_dictionary.json"
    with open(dict_path, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
    print(f"  Dictionnaire sauvegardé: {dict_path} ({len(dictionary)} entrées)")

    print("\n  Top 40 mots extraits:")
    for e in dictionary[:40]:
        print(f"    {e['source_word']:20s} -> {e['bassa_word']:20s} (count={e['count']})")

    print(f"\n=== Terminé! ===")
    print(f"  Prochaine étape: python scripts/seed_bible_jw.py")

    # Cleanup checkpoint on success
    if ckpt.exists():
        ckpt.unlink()


if __name__ == "__main__":
    main()
