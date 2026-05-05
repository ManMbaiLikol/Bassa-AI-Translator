"""Scrape Basaa dictionary from webonary.org/basaa.

Browses all entries alphabetically using the vernacular browse pages.
Uses cloudscraper to bypass Cloudflare protection.
Produces backend/seed/webonary_dictionary.json
"""
import json
import re
import sys
import time
from pathlib import Path

# Fix Windows console encoding for Bassa special characters
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import cloudscraper
except ImportError:
    print("cloudscraper required: pip install cloudscraper")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("beautifulsoup4 required: pip install beautifulsoup4 lxml")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "backend" / "seed"
BASE_URL = "https://www.webonary.org/basaa/browse/browse-vernacular-french/"
OUT_FILE = OUTPUT_DIR / "webonary_dictionary.json"

# All Bassa letters (standard + special characters)
LETTERS = [
    "a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m",
    "n", "o", "p", "r", "s", "t", "u", "v", "w", "y", "z",
    # Special Bassa characters (URL-encoded)
    "%C5%8B",    # ŋ
    "%C9%93",    # ɓ
    "%C9%94",    # ɔ
    "%C9%9B",    # ɛ
    "%E1%B7%87", # ḇ
]

PAGE_SIZE = 25
MAX_RETRIES = 4
RETRY_DELAYS = [5, 15, 30, 60]  # seconds between retries on 503


def clean(text):
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def parse_entries(html):
    """Parse all dictionary entries from a browse page."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for article in soup.find_all("div", class_="entry"):
        # Headword (Bassa)
        hw_span = article.find("span", class_="mainheadword")
        if not hw_span:
            continue
        hw_link = hw_span.find("a")
        bassa_word = clean(hw_link.get_text() if hw_link else hw_span.get_text())
        if not bassa_word:
            continue

        entry = {"bassa_word": bassa_word}

        # Plural form
        plural_span = article.find("span", class_="plural")
        if plural_span:
            entry["plural"] = clean(plural_span.get_text())

        # Part of speech
        pos_span = article.find("span", class_="graminfoabbrev")
        if pos_span:
            entry["category"] = clean(pos_span.get_text())

        # Collect all senses
        senses = []
        for sense in article.find_all("span", class_="sensecontent"):
            sense_data = {}

            fr_def = sense.find("span", class_="definitionorgloss")
            if fr_def:
                fr_text = fr_def.find("span", lang="fr")
                if fr_text:
                    sense_data["fr"] = clean(fr_text.get_text())

            en_def = sense.find("span", class_="definitionorgloss_1")
            if en_def:
                en_text = en_def.find("span", lang="en")
                if en_text:
                    sense_data["en"] = clean(en_text.get_text())

            de_def = sense.find("span", class_="definitionorgloss_2")
            if de_def:
                de_text = de_def.find("span", lang="de")
                if de_text:
                    sense_data["de"] = clean(de_text.get_text())

            ex_span = sense.find("span", class_="example")
            if ex_span:
                ex_bas = ex_span.find("span", lang="bas")
                if ex_bas:
                    sense_data["example_bassa"] = clean(ex_bas.get_text())

            tr_span = sense.find("span", class_="translation")
            if tr_span:
                tr_fr = tr_span.find("span", lang="fr")
                if tr_fr:
                    sense_data["example_fr"] = clean(tr_fr.get_text())

            if sense_data:
                senses.append(sense_data)

        entry["senses"] = senses
        entry["fr_definition"] = senses[0].get("fr", "") if senses else ""
        entry["en_definition"] = senses[0].get("en", "") if senses else ""
        entry["de_definition"] = senses[0].get("de", "") if senses else ""

        results.append(entry)

    return results


def fetch_with_retry(scraper, url):
    """GET url with retry on 503. Returns (response, ok) or (None, False)."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = scraper.get(url, timeout=25)
        except Exception as e:
            print(f"    Network error: {e}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[attempt]
                print(f"    Retrying in {delay}s...")
                time.sleep(delay)
            continue

        if resp.status_code == 200:
            return resp, True
        if resp.status_code == 404:
            return None, False
        if resp.status_code in (503, 429, 500):
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
            print(f"    HTTP {resp.status_code} — waiting {delay}s before retry...")
            time.sleep(delay)
            continue
        # Other error — skip
        print(f"    HTTP {resp.status_code} — skipping")
        return None, False

    print(f"    Gave up after {MAX_RETRIES} attempts")
    return None, False


def scrape_letter(letter, scraper):
    """Scrape all pages for a given letter."""
    params = f"?key=bas&letter={letter}&lang=en"
    all_entries = []
    page = 1

    while True:
        url = (f"{BASE_URL}{params}" if page == 1
               else f"{BASE_URL}page/{page}/{params}")

        resp, ok = fetch_with_retry(scraper, url)
        if not ok:
            break

        entries = parse_entries(resp.text)
        if not entries:
            break

        all_entries.extend(entries)
        print(f"    Page {page}: {len(entries)} entries")

        if len(entries) < PAGE_SIZE:
            break

        page += 1
        time.sleep(1.0)

    return all_entries


def save(entries):
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    print(f"  [saved {len(entries)} entries -> {OUT_FILE}]")


def main():
    print("=== Webonary.org Basaa Dictionary Scraper ===\n")

    # Load any previously saved data to allow resuming
    existing = []
    seen_words = set()
    if OUT_FILE.exists() and OUT_FILE.stat().st_size > 5:
        with open(OUT_FILE, encoding="utf-8") as f:
            existing = json.load(f)
        seen_words = {e["bassa_word"].lower() for e in existing}
        print(f"Resuming from {len(existing)} already-saved entries.\n")

    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

    all_entries = list(existing)

    for letter in LETTERS:
        print(f"Letter [{letter}]...")
        entries = scrape_letter(letter, scraper)

        added = 0
        for e in entries:
            key = e["bassa_word"].lower()
            if key not in seen_words:
                seen_words.add(key)
                all_entries.append(e)
                added += 1

        print(f"  -> {len(entries)} fetched, {added} new ({len(all_entries)} total)")

        # Save after each letter to avoid losing data
        if added > 0:
            save(all_entries)

        time.sleep(2.0)

    print(f"\n=== Done: {len(all_entries)} unique entries ===")
    save(all_entries)

    print("\nSample:")
    for e in all_entries[:10]:
        bw = e["bassa_word"][:18]
        cat = e.get("category", "")[:4]
        fr = e["fr_definition"][:45]
        print(f"  {bw:18s} | {cat:4s} | {fr}")


if __name__ == "__main__":
    main()
