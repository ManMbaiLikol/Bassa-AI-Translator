import fitz
import sys

def extract_pages(pdf_path, start_page, end_page, label):
    """Extract text from specific pages of a PDF."""
    separator = "=" * 80
    print(separator)
    print(f"  {label}")
    print(f"  File: {pdf_path}")
    print(f"  Pages: {start_page} to {end_page} (0-indexed)")
    print(separator)
    
    try:
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
    except Exception as e:
        print(f"  ERROR: {e}")
    
    print()

# 1. Bassa Bible - pages 20-25
extract_pages(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Bassa du Cameroun 2.pdf",
    20, 25,
    "BASSA BIBLE (Bible En Bassa du Cameroun 2.pdf)"
)

# 2. French Bible - pages 15-20
extract_pages(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En francais.pdf",
    15, 20,
    "FRENCH BIBLE (Bible En francais.pdf)"
)

# 3. English Bible - pages 15-20
extract_pages(
    r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Anglais 2.pdf",
    15, 20,
    "ENGLISH BIBLE (Bible En Anglais 2.pdf)"
)
