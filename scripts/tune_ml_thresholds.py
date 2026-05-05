"""Diagnostic et tuning des seuils du moteur ML.

Analyse la distribution des scores de similarité cosine sur le corpus réel
et recommande des valeurs optimales pour ML_HIGH_THRESHOLD et ML_MED_THRESHOLD.

Usage (depuis la racine du projet) :
    python scripts/tune_ml_thresholds.py
    python scripts/tune_ml_thresholds.py --lang fr
    python scripts/tune_ml_thresholds.py --high 0.90 --med 0.72 --simulate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import SessionLocal
from backend.models.corpus import CorpusPair
from backend.engine.ml_engine import MLEngine, _HAS_DEPS
from backend.config import settings


# ─────────────────────────────────────────────────────────────────────────────
# Phrases hors-domaine pour tester la spécificité
# ─────────────────────────────────────────────────────────────────────────────
OUT_OF_DOMAIN_FR = [
    "Je vais au marché acheter du pain et du lait",
    "Mon frère habite dans la ville depuis deux ans",
    "Le train arrive à la gare à quatorze heures trente",
    "Nous jouons au football avec les enfants de l'école",
    "La température aujourd'hui est de vingt-cinq degrés",
    "Il faut boire beaucoup d'eau pendant la saison sèche",
    "Ma mère prépare le repas pour toute la famille",
    "Les enfants apprennent à lire et à écrire à l'école",
    "Le médecin examine le patient à l'hôpital",
    "Nous construisons une nouvelle maison au village",
]

OUT_OF_DOMAIN_EN = [
    "I am going to the market to buy food",
    "My brother lives in the city since last year",
    "The train arrives at the station at two thirty",
    "We play football with the children from school",
    "The weather today is twenty five degrees",
]


def _bar(score: float, width: int = 30) -> str:
    filled = int(score * width)
    return "█" * filled + "░" * (width - filled)


def run_diagnostic(lang: str | None = None, high: float | None = None, med: float | None = None):
    if not _HAS_DEPS:
        print("ERREUR : sentence-transformers n'est pas installé.")
        sys.exit(1)

    print("Chargement du moteur ML...")
    engine = MLEngine()

    if not engine.model_ready:
        print("ERREUR : modèle non chargé ou corpus vide. Vérifiez la DB et les paires vérifiées.")
        sys.exit(1)

    high = high or settings.ML_HIGH_THRESHOLD
    med  = med  or settings.ML_MED_THRESHOLD

    print(f"\n{'='*60}")
    print(f"  Corpus : {engine.corpus_size} paires vérifiées")
    print(f"  Seuil actuel  HIGH = {settings.ML_HIGH_THRESHOLD}")
    print(f"  Seuil actuel  MED  = {settings.ML_MED_THRESHOLD}")
    print(f"  Seuil analysé HIGH = {high}")
    print(f"  Seuil analysé MED  = {med}")
    print(f"{'='*60}\n")

    db = SessionLocal()
    try:
        # Récupérer les paires vérifiées de la langue cible
        q = db.query(CorpusPair).filter(CorpusPair.is_verified == True)
        if lang:
            q = q.filter(CorpusPair.source_language == lang)
        pairs = q.all()

        if not pairs:
            print(f"Aucune paire vérifiée{f' (lang={lang})' if lang else ''}.")
            return

        # ── 1. Scores auto-similarité (exact match) ──────────────────────────
        print(f"── 1. SCORES EXACT MATCH ({len(pairs)} paires) ──")
        exact_scores = []
        for p in pairs:
            score, _, _ = engine._best_match(p.source_text, p.source_language)
            exact_scores.append(score)

        exact_min = min(exact_scores)
        exact_max = max(exact_scores)
        exact_mean = sum(exact_scores) / len(exact_scores)
        print(f"   min={exact_min:.4f}  max={exact_max:.4f}  mean={exact_mean:.4f}")
        if exact_min < 0.99:
            print(f"   ⚠  min < 0.99 : vérifier les entrées dupliquées ou les diacritiques.")
        else:
            print(f"   ✓  Toutes les phrases exactes scorent ≥ 0.99")

        # ── 2. Scores inter-paires (mêmes domaine) ────────────────────────────
        print(f"\n── 2. SCORES INTER-PAIRES (top 20 paires) ──")
        sample = pairs[:20]
        inter_scores = []
        false_positives_high = []
        false_positives_med  = []

        for i, p_query in enumerate(sample):
            # Chercher la meilleure correspondance en excluant la phrase exacte
            best = -1.0
            best_src = ""
            for j, p_corpus in enumerate(pairs):
                if i == j:
                    continue
                emb_q = engine._model.encode(
                    [p_query.source_text], convert_to_numpy=True, normalize_embeddings=True
                )
                emb_c = engine._model.encode(
                    [p_corpus.source_text], convert_to_numpy=True, normalize_embeddings=True
                )
                score = float((emb_q @ emb_c.T).flatten()[0])
                if score > best:
                    best = score
                    best_src = p_corpus.source_text

            inter_scores.append(best)
            if best >= high:
                false_positives_high.append((p_query.source_text, best_src, best))
            elif best >= med:
                false_positives_med.append((p_query.source_text, best_src, best))

        inter_mean = sum(inter_scores) / len(inter_scores)
        inter_max  = max(inter_scores)
        above_high = sum(1 for s in inter_scores if s >= high)
        above_med  = sum(1 for s in inter_scores if med <= s < high)

        print(f"   mean={inter_mean:.3f}  max={inter_max:.3f}")
        print(f"   Au-dessus HIGH({high}) = {above_high}/{len(sample)} → faux positifs retrieval")
        print(f"   Dans MED-HIGH          = {above_med}/{len(sample)} → suggestions")

        if false_positives_high:
            print(f"\n   ⚠  FAUX POSITIFS RETRIEVAL (score ≥ HIGH={high}) :")
            for q, matched, s in false_positives_high[:3]:
                print(f"     score={s:.3f}  query=«{q[:50]}»")
                print(f"            best =«{matched[:50]}»")
        else:
            print(f"\n   ✓  Aucun faux positif au niveau retrieval (HIGH={high})")

        # ── 3. Scores hors-domaine ────────────────────────────────────────────
        target_lang = lang or "fr"
        od_phrases = OUT_OF_DOMAIN_FR if target_lang == "fr" else OUT_OF_DOMAIN_EN
        print(f"\n── 3. SCORES HORS-DOMAINE ({len(od_phrases)} phrases) ──")

        od_scores = []
        od_above_med = []
        for text in od_phrases:
            score, matched_src, _ = engine._best_match(text, target_lang)
            od_scores.append(score)
            bar = _bar(score)
            flag = " ⚠  MED!" if score >= med else ("  HIGH!" if score >= high else "")
            print(f"   {score:.3f} {bar} {flag}")
            print(f"          query=«{text[:55]}»")
            print(f"          best =«{matched_src[:55].encode('ascii','replace').decode()}»")
            if score >= med:
                od_above_med.append((text, score))

        od_max  = max(od_scores)
        od_mean = sum(od_scores) / len(od_scores)
        print(f"\n   max={od_max:.3f}  mean={od_mean:.3f}")
        if od_above_med:
            print(f"   ⚠  {len(od_above_med)} phrase(s) hors-domaine au-dessus de MED={med}")
        else:
            print(f"   ✓  Toutes les phrases hors-domaine sous MED={med}")

        # ── 4. Recommandation ─────────────────────────────────────────────────
        print(f"\n── 4. RECOMMANDATION ──")

        # HIGH : juste au-dessus du max inter-paires pour éviter les faux positifs
        rec_high = round(max(inter_scores) + 0.03, 2)
        rec_high = min(rec_high, 0.99)

        # MED : juste au-dessus du max hors-domaine pour réduire le bruit
        rec_med = round(od_max + 0.05, 2)
        rec_med = max(rec_med, 0.50)
        rec_med = min(rec_med, rec_high - 0.05)

        print(f"   Inter-paires max = {max(inter_scores):.3f}")
        print(f"   Hors-domaine max = {od_max:.3f}")
        print()
        print(f"   ML_HIGH_THRESHOLD recommandé : {rec_high}  (actuellement {settings.ML_HIGH_THRESHOLD})")
        print(f"   ML_MED_THRESHOLD  recommandé : {rec_med}  (actuellement {settings.ML_MED_THRESHOLD})")
        print()

        if rec_high != settings.ML_HIGH_THRESHOLD or rec_med != settings.ML_MED_THRESHOLD:
            print("   Pour appliquer, modifier le .env :")
            print(f"     ML_HIGH_THRESHOLD={rec_high}")
            print(f"     ML_MED_THRESHOLD={rec_med}")
        else:
            print("   ✓  Les seuils actuels correspondent aux recommandations.")

    finally:
        db.close()


def simulate(high: float, med: float):
    """Simule le comportement du moteur avec de nouveaux seuils."""
    print(f"\n── SIMULATION HIGH={high}  MED={med} ──")

    engine = MLEngine()
    if not engine.model_ready:
        print("Moteur ML non disponible.")
        return

    test_phrases = [
        ("La terre était informe et déserte", "fr", "phrase biblique"),
        ("Dieu vit que la lumière était bonne", "fr", "verset similaire"),
        ("Au commencement Dieu créa le ciel", "fr", "même domaine"),
        ("Je mange du riz avec ma famille", "fr", "hors-domaine"),
        ("Bonjour à tous", "fr", "hors-domaine quotidien"),
    ]

    for text, lang, label in test_phrases:
        score, matched, _ = engine._best_match(text, lang)
        if score >= high:
            decision = "RETRIEVAL"
        elif score >= med:
            decision = "SUGGESTION"
        else:
            decision = "dict seul"
        print(f"   [{decision:10}] score={score:.3f}  ({label})")
        print(f"                    query=«{text[:50]}»")


def main():
    parser = argparse.ArgumentParser(description="Diagnostic seuils ML — BassaAI")
    parser.add_argument("--lang", default=None, choices=["fr", "en"], help="Filtrer par langue")
    parser.add_argument("--high", type=float, default=None, help="Seuil HIGH à analyser")
    parser.add_argument("--med",  type=float, default=None, help="Seuil MED à analyser")
    parser.add_argument("--simulate", action="store_true", help="Simuler avec les seuils fournis")
    args = parser.parse_args()

    run_diagnostic(lang=args.lang, high=args.high, med=args.med)

    if args.simulate and args.high and args.med:
        simulate(args.high, args.med)


if __name__ == "__main__":
    main()
