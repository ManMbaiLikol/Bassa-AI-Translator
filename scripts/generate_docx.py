"""Génère le fichier Word 'état des besoins moteur de traduction'."""
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# ── Couleurs ─────────────────────────────────────────────────────
GREEN_DARK = RGBColor(0x1B, 0x43, 0x32)
GREEN      = RGBColor(0x2D, 0x6A, 0x4F)
RED        = RGBColor(0xDC, 0x26, 0x26)
ORANGE     = RGBColor(0xD9, 0x77, 0x06)
GREY_TEXT  = RGBColor(0x6B, 0x7C, 0x6E)
WHITE      = RGBColor(0xFF, 0xFF, 0xFF)

# ── Marges ───────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin   = Cm(3.0)
    section.right_margin  = Cm(2.5)

# ── Helpers ───────────────────────────────────────────────────────
def set_cell_bg(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)


def h(text, level=1, color=GREEN_DARK):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        run.font.color.rgb = color
        run.font.name = "Calibri"
    return p


def body(text, bold=False, italic=False, color=None, size=Pt(11)):
    p   = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size   = size
    run.font.bold   = bold
    run.font.italic = italic
    run.font.name   = "Calibri"
    if color:
        run.font.color.rgb = color
    return p


def bullet(text):
    p   = doc.add_paragraph(style="List Bullet")
    run = p.add_run(text)
    run.font.size = Pt(11)
    run.font.name = "Calibri"
    return p


def table(headers, rows, hdr_bg="1B4332", col_widths=None):
    tbl = doc.add_table(rows=1, cols=len(headers))
    tbl.style     = "Table Grid"
    tbl.alignment = WD_TABLE_ALIGNMENT.LEFT

    hdr_cells = tbl.rows[0].cells
    for i, txt in enumerate(headers):
        hdr_cells[i].text = txt
        set_cell_bg(hdr_cells[i], hdr_bg)
        run = hdr_cells[i].paragraphs[0].runs[0]
        run.font.bold      = True
        run.font.color.rgb = WHITE
        run.font.size      = Pt(10)
        run.font.name      = "Calibri"

    for row_data in rows:
        cells = tbl.add_row().cells
        for i, val in enumerate(row_data):
            cells[i].text = str(val)
            run = cells[i].paragraphs[0].runs[0]
            run.font.size = Pt(10)
            run.font.name = "Calibri"

    if col_widths:
        for row in tbl.rows:
            for j, cell in enumerate(row.cells):
                cell.width = Cm(col_widths[j])
    return tbl


def spacer():
    doc.add_paragraph()


# ════════════════════════════════════════════════════════════════════
# PAGE DE TITRE
# ════════════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("BassaAI Translator")
run.font.size  = Pt(26)
run.font.bold  = True
run.font.color.rgb = GREEN_DARK
run.font.name  = "Calibri"

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
run2 = p2.add_run("Etat des besoins — Moteur de traduction")
run2.font.size  = Pt(16)
run2.font.color.rgb = GREEN
run2.font.name  = "Calibri"

p3 = doc.add_paragraph()
p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
run3 = p3.add_run("Traduction automatique FR/EN -> Bassa (Mbelel)")
run3.font.size   = Pt(12)
run3.font.italic = True
run3.font.color.rgb = GREY_TEXT
run3.font.name   = "Calibri"

p4 = doc.add_paragraph()
p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
run4 = p4.add_run("2 avril 2026")
run4.font.size  = Pt(11)
run4.font.color.rgb = GREY_TEXT
run4.font.name  = "Calibri"

doc.add_page_break()

# ════════════════════════════════════════════════════════════════════
# RESUME EXECUTIF
# ════════════════════════════════════════════════════════════════════
h("Resume executif", level=1)
body(
    "Le moteur de traduction repose sur trois composantes : un dictionnaire bilingue, "
    "un corpus de phrases paralleles, et un modele IA (Claude). L'analyse de la base "
    "de donnees revele que la qualite des traductions est aujourd'hui limitee non par "
    "la technologie, mais par le volume et la diversite des donnees linguistiques "
    "disponibles. Les actions prioritaires sont la verification du corpus existant et "
    "l'ajout de paires dans des domaines de la vie quotidienne."
)
spacer()

# ════════════════════════════════════════════════════════════════════
# 1. CORPUS
# ════════════════════════════════════════════════════════════════════
h("1. Corpus parallele — Probleme critique", level=1)
h("Etat actuel", level=2, color=GREEN)

table(
    ["Indicateur", "Valeur actuelle", "Cible recommandee"],
    [
        ["Paires totales",                  "4 915",       "20 000+"],
        ["Paires verifiees (actives)",       "155  (3 %)",  ">= 16 000  (80 %+)"],
        ["Paires en francais (FR)",          "4 915",       "15 000+"],
        ["Paires en anglais (EN)",           "0",           "2 000+"],
        ["Domaines couverts",                "1  (Bible)",  "10+"],
        ["Longueur moyenne des phrases",     "144 car.",    "Mix 20-200 car."],
    ],
    col_widths=[7, 4.5, 4.5],
)
spacer()
h("Pourquoi c'est bloquant", level=2, color=GREEN)
body("Le moteur ML et le moteur LLM n'utilisent que les paires verifiees. Avec 155 paires actives sur 4 915 :")
bullet("L'index ML couvre moins de 3 % du corpus disponible.")
bullet("Claude ne recoit que des exemples de style biblique — il calque ses traductions sur ce registre meme pour des phrases du quotidien.")
bullet("L'anglais -> Bassa fonctionne uniquement avec le dictionnaire : aucun exemple de traduction complete n'est disponible pour le ML ni pour Claude.")
spacer()
h("Ce qu'il faut faire", level=2, color=GREEN)
bullet("Verifier les 4 760 paires non-verifiees (relecture + correction par un locuteur Bassa) — cette seule action multiplierait par 31 la taille de l'index ML.")
bullet("Creer des paires en anglais : au moins 2 000 paires EN->Bassa couvrant les domaines prioritaires.")
spacer()

# ════════════════════════════════════════════════════════════════════
# 2. DOMAINES
# ════════════════════════════════════════════════════════════════════
h("2. Diversite des domaines — Manque total", level=1)
body("100 % du corpus actuel provient de la Bible. Le moteur excelle a traduire les textes religieux mais echoue sur le langage courant.")
spacer()
table(
    ["Domaine", "Priorite", "Exemples de phrases types"],
    [
        ["Vie quotidienne / famille",   "Critique",  "Salutations, repas, maison, enfants, voisinage"],
        ["Sante / corps humain",        "Critique",  "Maladie, medecin, symptomes, soins, maternite"],
        ["Agriculture / nature",        "Haute",     "Cultures locales, saisons, animaux, foret"],
        ["Commerce / echanges",         "Haute",     "Marche, prix, argent, acheter/vendre"],
        ["Education / ecole",           "Haute",     "Apprendre, compter, lire, enseignant, eleve"],
        ["Administration / communaute", "Moyenne",   "Identite, village, chef, reunion, accord"],
        ["Emotions / etats interieurs", "Moyenne",   "Joie, peur, tristesse, faim, fatigue, amour"],
        ["Proverbes et expressions",    "Moyenne",   "Sagesse populaire, idiomes Bassa, formules figees"],
        ["Tourisme / geographie",       "Basse",     "Regions du Cameroun, routes, directions, lieux"],
        ["Droit / justice",             "Basse",     "Loi coutumiere, mariage, heritage, conflit"],
    ],
    col_widths=[5, 3, 8],
)
spacer()
body("Pour un moteur ML efficace, chaque domaine a besoin d'au moins 200 paires verifiees (phrases completes).")
spacer()

# ════════════════════════════════════════════════════════════════════
# 3. DICTIONNAIRE
# ════════════════════════════════════════════════════════════════════
h("3. Dictionnaire — Qualites et lacunes", level=1)
h("Ce qui est satisfaisant", level=2, color=GREEN)
bullet("32 130 entrees au total — volume consequent.")
bullet("98 % verifiees (31 605 entrees) — fiabilite elevee.")
bullet("Bonne couverture francaise : 16 480 entrees.")
spacer()

h("3.1  Phonetique absente (critique pour les tons)", level=2, color=RED)
table(
    ["Indicateur", "Valeur"],
    [
        ["Entrees avec phonetique renseignee", "44 sur 32 130  (0,1 %)"],
        ["Entrees sans information tonale",    "32 086  (99,9 %)"],
    ],
    col_widths=[9, 7],
)
spacer()
body(
    "Le Bassa est une langue tonale : un meme mot peut avoir des sens differents selon le ton "
    "(haut, moyen, bas). Sans les marques tonales, le LLM et les utilisateurs ne peuvent pas "
    "savoir quelle forme est correcte pour chaque entree."
)
spacer()

h("3.2  Couverture anglais insuffisante", level=2, color=ORANGE)
table(
    ["Langue", "Entrees", "% du total"],
    [
        ["Francais (FR)", "16 480", "51 %"],
        ["Anglais (EN)",  "7 437",  "23 %"],
        ["Autres / non classe", "~8 213", "26 %"],
    ],
    col_widths=[5, 4, 4],
)
spacer()
body("Objectif : atteindre la parite FR/EN (>= 16 000 entrees anglais).")
spacer()

h("3.3  Incoherence des categories grammaticales", level=2, color=ORANGE)
table(
    ["Code en base", "Signification", "Code interface admin"],
    [
        ["s",    "Substantif / nom",   "noun"],
        ["v",    "Verbe",              "verb"],
        ["loc",  "Locution",           "(absent)"],
        ["q",    "Interrogatif",       "(absent)"],
        ["npro", "Nom propre",         "(absent)"],
        ["adv",  "Adverbe",            "adverb"],
        ["ono",  "Onomatopee",         "(absent)"],
    ],
    col_widths=[4, 5, 5],
)
spacer()
body("Une migration de normalisation est necessaire pour unifier les codes entre la base de donnees et l'interface.")
spacer()

# ════════════════════════════════════════════════════════════════════
# 4. REGLES GRAMMATICALES
# ════════════════════════════════════════════════════════════════════
h("4. Regles grammaticales — Non renseignees", level=1)
body(
    "La fonctionnalite de regles grammaticales dynamiques (table grammatical_rules, editables "
    "depuis l'interface admin) vient d'etre creee. Elle contient actuellement 0 regle, alors "
    "que c'est le levier le plus accessible pour ameliorer le LLM sans toucher au code."
)
spacer()
table(
    ["Langue", "Nom de la regle", "Patron source", "Transformation Bassa"],
    [
        ["FR",    "Negation ne...pas",      "ne + verbe + pas",     "verbe + be (post-verbal)"],
        ["FR",    "Article defini/indefini","le/la/les/un/une",     "Supprimer"],
        ["FR",    "Adjectif epithete",      "adj + nom",            "nom + adj (ordre inverse)"],
        ["FR",    "Possessif",              "son/sa/mes + nom",     "nom + possessif"],
        ["EN",    "Negation (not/n't)",     "verb + not",           "verbe + be (post-verbal)"],
        ["EN",    "Articles",               "the / a / an",         "Supprimer"],
        ["EN",    "Progressif (-ing)",      "is/are + verb-ing",    "prefixe ng- + verbe"],
        ["EN",    "Passe simple",           "verb-ed / irreguliers","prefixe a- + verbe"],
        ["FR/EN", "Salutation formelle",    "bonjour / hello",      "Forme Bassa contextuelle"],
        ["FR/EN", "Interrogation directe",  "est-ce que / is/are",  "Structure question Bassa"],
    ],
    col_widths=[2.2, 4.3, 4.3, 5.2],
)
spacer()

# ════════════════════════════════════════════════════════════════════
# 5. DONNEES QUALITATIVES
# ════════════════════════════════════════════════════════════════════
h("5. Donnees qualitatives — Role des locuteurs natifs", level=1)
body("Ces points ne peuvent pas etre resolus par la technologie seule : ils requierent l'intervention de locuteurs natifs Bassa ou de linguistes specialises.")
spacer()
table(
    ["Besoin", "Description", "Urgence"],
    [
        ["Validation corpus",    "Relecture et correction des 4 760 paires non-verifiees",              "Critique"],
        ["Tons et diacritiques", "Ajout des marques tonales sur les entrees du dictionnaire",            "Haute"],
        ["Corpus quotidien",     "Creation de dialogues simples, conversations de la vie courante",      "Haute"],
        ["Correction LLM",       "Identifier les erreurs typiques de Claude et les corriger dans le corpus", "Haute"],
        ["Proverbes et oral",    "Collecte d'expressions figees, proverbes, formules de politesse",      "Moyenne"],
        ["Validation finale",    "Revue humaine systematique avant tout usage officiel",                 "Continue"],
    ],
    col_widths=[4.5, 7.5, 3],
)
spacer()

# ════════════════════════════════════════════════════════════════════
# 6. PLAN D'ACTION
# ════════════════════════════════════════════════════════════════════
h("6. Plan d'action — Resume priorise", level=1)

sections = [
    ("Priorite 1 — Critique (impact immediat)", [
        "Verifier les 4 760 paires corpus existantes (Admin > Corpus)",
        "Creer un minimum de 500 paires EN->Bassa dans les domaines quotidien / sante / famille",
        "Saisir les 10 regles grammaticales prioritaires dans l'Admin > Regles",
    ]),
    ("Priorite 2 — Haute (ameliore fortement la qualite Claude)", [
        "Etendre le corpus FR avec des domaines hors Bible (agriculture, commerce, education)",
        "Completer les phonetiques des 1 000 mots les plus frequents du dictionnaire",
        "Ajouter des exemples de phrases aux entrees dictionnaire cles",
    ]),
    ("Priorite 3 — Moyenne (enrichissement continu)", [
        "Normaliser les categories grammaticales (s -> noun, v -> verb, etc.)",
        "Collecter des proverbes et expressions idiomatiques Bassa",
        "Atteindre la parite FR/EN dans le dictionnaire (objectif : 16 000 entrees EN)",
    ]),
    ("Priorite 4 — Continue", [
        "Utiliser le mecanisme de feedback (pouce haut/bas) pour alimenter le corpus via les utilisateurs",
        "Organiser des sessions de contribution avec des locuteurs natifs",
        "Mettre en place une revue trimestrielle de la qualite des traductions",
    ]),
]

for titre, items in sections:
    h(titre, level=2, color=GREEN)
    for item in items:
        bullet("[ ]  " + item)
    spacer()

# ════════════════════════════════════════════════════════════════════
# 7. INDICATEURS DE SUIVI
# ════════════════════════════════════════════════════════════════════
h("7. Indicateurs de suivi", level=1)
table(
    ["Indicateur", "Actuel", "Objectif 3 mois", "Objectif 1 an"],
    [
        ["Paires corpus verifiees",                "155",     "4 000",  "15 000"],
        ["Paires EN dans le corpus",               "0",       "500",    "2 000"],
        ["Domaines couverts",                      "1",       "5",      "10+"],
        ["Regles grammaticales actives",           "0",       "11",     "30+"],
        ["Entrees dictionnaire avec phonetique",   "44",      "1 000",  "10 000"],
        ["Score confiance moyen moteur ML",        "~30 %",   "~60 %",  "~80 %"],
    ],
    col_widths=[6.5, 2.5, 3.5, 3.5],
)
spacer()

# ── Pied de page ─────────────────────────────────────────────────
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("Document genere le 2 avril 2026 — BassaAI Translator v2.0")
run.font.size   = Pt(9)
run.font.italic = True
run.font.color.rgb = GREY_TEXT
run.font.name   = "Calibri"

# ── Sauvegarde ───────────────────────────────────────────────────
out = r"C:\wamp64\www\Bassa_AI_Translator\Docs\etat_besoins_moteur_traduction.docx"
doc.save(out)
print("Fichier cree :", out)
