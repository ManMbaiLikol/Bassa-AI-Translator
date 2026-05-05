import fitz
import sys
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def extract_pages(pdf_path, start_page, end_page, label):
    """Extract text from specific pages of a PDF."""
    separator = "=" * 80
    print(separator)
    print(f"  {label}")
    print(f"  File: {pdf_path}")
    print(f"  Pages: {start_page} to {end_page} (0-indexed)")
    print(separator)
    
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    print(f"  Total pages in PDF: {total_pages}\n")
    
    for page_num in range(start_page, min(end_page + 1, total_pages)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        
        print(f"--- PAGE {page_num} (PDF page {page_num + 1}) ---")
        print(text)
        print()
    
    doc.close()
    print()

def find_genesis_page(pdf_path, search_terms, scan_range=(0, 100)):
    """Scan pages to find where Genesis chapter 1 actually starts."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    end = min(scan_range[1], total_pages)
    
    print(f"  Scanning pages {scan_range[0]}-{end} for: {search_terms}")
    
    found_pages = []
    for page_num in range(scan_range[0], end):
        page = doc.load_page(page_num)
        text = page.get_text("text").lower()
        for term in search_terms:
            if term.lower() in text:
                # Check if this looks like actual verse content (not TOC)
                snippet = page.get_text("text")[:200].replace('\n', ' ')
                found_pages.append((page_num, term, snippet))
                break
    
    doc.close()
    return found_pages

# First, let's find where Genesis actually starts in each Bible
print("=" * 80)
print("  SEARCHING FOR GENESIS / BIB'ODLE IN EACH PDF")
print("=" * 80)
print()

# Bassa Bible - search for Genesis-related terms
print("--- BASSA BIBLE ---")
bassa_results = find_genesis_page(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Bassa du Cameroun 2.pdf",
    ["bib'odle", "bibôdle", "genèse", "i bibôd", "bibod", "bibodle", "ndap yo ini"],
    (0, 150)
)
for pg, term, snippet in bassa_results:
    print(f"  Page {pg}: found '{term}' -> {snippet[:120]}...")
print()

# French Bible
print("--- FRENCH BIBLE ---")
french_results = find_genesis_page(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En francais.pdf",
    ["genèse", "genesis", "au commencement", "dieu créa"],
    (0, 100)
)
for pg, term, snippet in french_results:
    print(f"  Page {pg}: found '{term}' -> {snippet[:120]}...")
print()

# English Bible
print("--- ENGLISH BIBLE ---")
english_results = find_genesis_page(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Anglais 2.pdf",
    ["genesis", "in the beginning", "god created"],
    (0, 100)
)
for pg, term, snippet in english_results:
    print(f"  Page {pg}: found '{term}' -> {snippet[:120]}...")
print()

