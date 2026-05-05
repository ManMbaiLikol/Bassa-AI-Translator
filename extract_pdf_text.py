import fitz  # PyMuPDF
import os
import sys

# Force UTF-8 output on Windows
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Define the PDFs and how many pages to extract from each
pdfs = [
    (r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Bassa du Cameroun.pdf", 10),
    (r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Bassa du Cameroun 2.pdf", 10),
    (r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En francais.pdf", 10),
    (r"C:\wamp64\www\Bassa_AI_Translator\Docs\Bible En Anglais.pdf", 5),
]

for filepath, num_pages in pdfs:
    filename = os.path.basename(filepath)
    separator = "=" * 80
    print(f"\n{separator}")
    print(f"  FILE: {filename}")
    print(f"  Extracting first {num_pages} pages")
    print(f"{separator}\n")

    if not os.path.exists(filepath):
        print(f"  [ERROR] File not found: {filepath}\n")
        continue

    try:
        doc = fitz.open(filepath)
        total_pages = len(doc)
        pages_to_read = min(num_pages, total_pages)
        print(f"  Total pages in document: {total_pages}")
        print(f"  Reading pages: 1 to {pages_to_read}\n")

        for page_num in range(pages_to_read):
            page = doc[page_num]
            text = page.get_text()
            print(f"--- Page {page_num + 1} ---")
            if text.strip():
                print(text)
            else:
                print("  [No extractable text on this page]\n")

        doc.close()
    except Exception as e:
        print(f"  [ERROR] Could not process {filename}: {e}\n")

print("\n" + "=" * 80)
print("  EXTRACTION COMPLETE")
print("=" * 80)
