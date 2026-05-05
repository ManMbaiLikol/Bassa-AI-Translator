"""Phase 3: Moteur LLM — traduction contextuelle via Claude API.

Fonctionnement :
  1. Extrait du dictionnaire les entrées pertinentes pour les mots du texte.
  2. Récupère des exemples proches depuis le corpus (via le moteur ML si dispo).
  3. Charge les règles grammaticales Bassa depuis la DB (GrammaticalRule).
  4. Envoie un prompt structuré à Claude (system + user) avec ce contexte.
  5. Retourne la traduction générée, enrichie du découpage mot-à-mot du dictionnaire.

Cercle vertueux :
  - Dictionnaire et corpus grandissent via contributions communautaires
  - Règles grammaticales éditables depuis l'interface admin
  - Traductions validées (feedback 👍) enrichissent le corpus
  → le contexte fourni à Claude s'améliore continuellement
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry
from backend.models.grammar import GrammaticalRule
from backend.engine.base import TranslationEngine, TranslationResult
from backend.engine.dictionary_engine import DictionaryEngine, normalize_bassa, FR_LEMMAS, EN_LEMMAS
from backend.engine.tokenizer import tokenize
from backend.services import corpus as corpus_service

logger = logging.getLogger(__name__)

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False
    logger.warning(
        "Le package 'anthropic' est manquant. "
        "Installez-le avec: pip install anthropic\n"
        "Le moteur LLM ne sera pas disponible."
    )

# Nombre maximal d'entrées du dictionnaire injectées dans le prompt
_MAX_DICT_ENTRIES = 60
# Nombre maximal d'exemples corpus injectés dans le prompt
_MAX_CORPUS_EXAMPLES = 10


# ── Prompt système : expertise linguistique Bassa ─────────────────────────────
_SYSTEM_PROMPT = """Tu es un expert en linguistique de la langue Bassa (Mbɛlɛ̂), langue bantoue (famille B51) parlée par environ 700 000 personnes dans les régions du Centre et du Littoral du Cameroun. Tu traduis exclusivement du français ou de l'anglais vers le Bassa avec précision linguistique.

## Phonologie Bassa
- Langue tonale : les tons sont phonémiques (porteurs de sens distincts)
- Consonnes spéciales : ɓ (implosive bilabiale), ɗ (implosive alvéolaire), ŋ (nasale vélaire), ɲ (nasale palatale)
- Voyelles : a, e, ɛ, i, o, ɔ, u — avec variantes tonales (â, ê, ô, î, ɛ̂, etc.)
- Les diacritiques et marques tonales sont sémantiquement essentiels — les respecter rigoureusement (Unicode NFC)

## Structure grammaticale
- Ordre des constituants : **Sujet – Verbe – Objet** (SVO), identique au français
- **Pas d'articles** définis ni indéfinis : "le/la/les/un/une/des/du/the/a/an" ne se traduisent pas
- Adjectifs épithètes : placés **APRÈS** le nom (contraire du français)
- Possessifs : placés **APRÈS** le nom

## Morphologie verbale (préfixes)
- Présent/habituel : préfixe **ŋ-** sur la racine verbale (ex: ŋ-âŋ = lit)
- Passé/accompli : préfixe **a-** suivi de ŋ- aspectuel possible (ex: a-ŋ-âŋ = a lu)
- Futur : construction avec **ka** ou suffixe verbal selon le contexte dialectal
- L'accord du sujet peut se marquer par un préfixe pronominal sur le verbe

## Pronoms personnels
- 1ère sg : **mè** (je / me)
- 2ème sg : **ô** (tu / te)
- 3ème sg : **ɓé** ou **o** (il / elle / lui)
- 1ère pl : **bɛ̈** (nous)
- 2ème pl : **biŋ** (vous)
- 3ème pl : **bé** (ils / elles)

## Négation (règle essentielle)
- Marqueur post-verbal : **ɓé** placé **APRÈS** le verbe (et avant le complément)
- "Ne…pas" (FR) / "not / n't" (EN) → [sujet] [verbe] **ɓé** [complément]
- Exemple confirmé : « Kɛlâm a-ŋ-âŋ ɓé kaat » = « Kelam ne lit pas de livre »

## Règles de traduction
1. Utiliser en priorité le vocabulaire du **dictionnaire fourni** pour les mots connus
2. S'appuyer sur les **exemples du corpus** comme modèles syntaxiques concrets
3. Respecter les **règles spécifiques** fournies dans le contexte
4. Ne jamais translittérer : chercher l'équivalent sémantique Bassa, jamais la transcription phonétique
5. Produire une traduction **naturelle** en Bassa, pas une traduction littérale mot-à-mot
6. Retourner **UNIQUEMENT** la traduction Bassa — aucun commentaire, aucune explication, aucune romanisation en parallèle
7. Pour les mots sans équivalent direct, proposer une périphrase descriptive en Bassa"""


class LLMEngine(TranslationEngine):
    """Moteur de traduction basé sur Claude avec contexte dictionnaire + corpus + règles DB.

    Paramètres
    ----------
    api_key : str
        Clé API Anthropic.
    fallback_engine : TranslationEngine | None
        Moteur de secours (MLEngine ou DictionaryEngine) utilisé en cas
        d'erreur API ou d'indisponibilité du réseau.
    dict_engine : DictionaryEngine | None
        Instance partagée du moteur dictionnaire. Si None, une nouvelle instance
        est créée. Passer l'instance existante évite de charger le dictionnaire
        en RAM plusieurs fois.
    """

    def __init__(
        self,
        api_key: str,
        fallback_engine: TranslationEngine | None = None,
        dict_engine: DictionaryEngine | None = None,
    ):
        if not _HAS_ANTHROPIC:
            raise RuntimeError(
                "Le package 'anthropic' est requis pour le moteur LLM. "
                "Installez-le avec: pip install anthropic"
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._fallback = fallback_engine

        # Si un moteur dictionnaire est fourni, on le partage (pas de double chargement).
        # _owns_dict_engine=False signifie que le rechargement est géré de l'extérieur.
        if dict_engine is not None:
            self._dict_engine = dict_engine
            self._owns_dict_engine = False
        else:
            self._dict_engine = DictionaryEngine()
            self._owns_dict_engine = True

        # Caches en mémoire pour éviter les erreurs SQLAlchemy de session détachée
        self._dict_cache: list[dict] = []
        self._corpus_cache: list[dict] = []
        self._grammar_rules: list[dict] = []  # règles de la table GrammaticalRule

        # Cache de traductions LLM : évite des appels API répétés pour un même texte.
        # Invalidé à chaque reload() (nouveau corpus ou nouvelles règles).
        self._response_cache: dict[tuple[str, str], TranslationResult] = {}

        self.reload()

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def reload(self, db: Session = None) -> None:
        """Recharge le dictionnaire (si possédé), le corpus, les règles DB et le moteur de secours."""
        if self._owns_dict_engine:
            self._dict_engine.reload(db)
        if self._fallback is not None:
            self._fallback.reload(db)

        # Invalider le cache de réponses : le contexte (corpus, règles) a changé
        self._response_cache.clear()

        own_session = db is None
        if own_session:
            db = SessionLocal()
        try:
            self._dict_cache = [
                {
                    "source_word": e.source_word,
                    "bassa_word": e.bassa_word,
                    "phonetic": e.phonetic or "",
                    "category": e.category or "",
                    "source_language": e.source_language,
                }
                for e in db.query(DictionaryEntry).all()
            ]
            self._corpus_cache = [
                {
                    "source_text": p.source_text,
                    "bassa_text": normalize_bassa(p.bassa_text),
                    "source_language": p.source_language,
                }
                for p in corpus_service.get_all_verified(db)
            ]
            self._grammar_rules = [
                {
                    "rule_name": r.rule_name,
                    "source_language": r.source_language,
                    "pattern": r.pattern,
                    "transformation": r.transformation,
                }
                for r in db.query(GrammaticalRule)
                .filter(GrammaticalRule.is_active == True)
                .order_by(GrammaticalRule.priority)
                .all()
            ]
        finally:
            if own_session:
                db.close()

        logger.info(
            "LLMEngine rechargé : %d entrées dictionnaire, %d paires corpus, %d règles DB.",
            len(self._dict_cache),
            len(self._corpus_cache),
            len(self._grammar_rules),
        )

    # ------------------------------------------------------------------
    # Construction du contexte pour le prompt utilisateur
    # ------------------------------------------------------------------

    def _relevant_dict_entries(self, text: str, lang: str) -> list[dict]:
        """Sélectionne les entrées du dictionnaire pertinentes pour le texte."""
        tokens = set(tokenize(text, lang))
        lemma_map = FR_LEMMAS if lang == "fr" else EN_LEMMAS

        expanded = set(tokens)
        for t in tokens:
            base = lemma_map.get(t.lower())
            if base:
                expanded.add(base)

        matched = [
            e for e in self._dict_cache
            if e["source_language"] == lang and e["source_word"].lower() in expanded
        ]

        if len(matched) < _MAX_DICT_ENTRIES:
            seen = {e["source_word"] for e in matched}
            for e in self._dict_cache:
                if e["source_language"] == lang and e["source_word"] not in seen:
                    matched.append(e)
                    seen.add(e["source_word"])
                    if len(matched) >= _MAX_DICT_ENTRIES:
                        break

        return matched[:_MAX_DICT_ENTRIES]

    def _relevant_corpus_examples(self, text: str, lang: str) -> list[dict]:
        """Récupère des exemples corpus pertinents via recherche sémantique (ML) ou brute."""
        lang_pairs = [p for p in self._corpus_cache if p["source_language"] == lang]

        try:
            from backend.engine.ml_engine import MLEngine
            if isinstance(self._fallback, MLEngine) and self._fallback.model_ready:
                import numpy as np
                query = self._fallback._model.encode(
                    [text], convert_to_numpy=True, normalize_embeddings=True
                )
                # flatten() garantit un tableau 1D même avec 1 seule paire corpus
                # (squeeze() retourne un scalaire 0-D, incompatible avec l'indexation)
                scores = (self._fallback._embeddings @ query.T).flatten()

                indexed = [
                    (float(scores[i]), i)
                    for i, l in enumerate(self._fallback._langs)
                    if l == lang
                ]
                indexed.sort(reverse=True)

                results = []
                for score, idx in indexed[:_MAX_CORPUS_EXAMPLES]:
                    if score > 0.25:
                        results.append({
                            "source_text": self._fallback._sources[idx],
                            "bassa_text": self._fallback._bassa[idx],
                        })
                if results:
                    return results
        except Exception:
            pass

        return lang_pairs[:_MAX_CORPUS_EXAMPLES]

    def _build_user_message(self, text: str, lang: str) -> str:
        """Construit le message utilisateur : contexte dictionnaire + corpus + règles DB + texte."""
        lang_label = "français" if lang == "fr" else "anglais"
        entries = self._relevant_dict_entries(text, lang)
        examples = self._relevant_corpus_examples(text, lang)

        blocks: list[str] = []

        # Bloc dictionnaire
        if entries:
            lines = []
            for e in entries:
                line = f"  {e['source_word']} → {e['bassa_word']}"
                if e["phonetic"]:
                    line += f" /{e['phonetic']}/"
                if e["category"]:
                    line += f" [{e['category']}]"
                lines.append(line)
            blocks.append("### Dictionnaire " + lang_label.upper() + " → Bassa\n" + "\n".join(lines))

        # Bloc corpus
        if examples:
            lines = [
                f"  {ex['source_text']}\n  → {ex['bassa_text']}"
                for ex in examples
            ]
            blocks.append("### Exemples de traduction (corpus parallèle)\n" + "\n\n".join(lines))

        # Bloc règles DB
        db_rules = [r for r in self._grammar_rules if r["source_language"] == lang]
        if db_rules:
            lines = [
                f"  • {r['rule_name']} : {r['pattern']} → {r['transformation']}"
                for r in db_rules
            ]
            blocks.append("### Règles grammaticales spécifiques\n" + "\n".join(lines))

        context = "\n\n".join(blocks)

        return (
            f"{context}\n\n"
            f"---\n"
            f"Traduis ce texte {lang_label} en Bassa :\n\n"
            f"{text}\n\n"
            f"Traduction Bassa :"
        )

    # ------------------------------------------------------------------
    # Traduction
    # ------------------------------------------------------------------

    def translate(self, text: str, source_language: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                source_text=text,
                translated_text="",
                source_language=source_language,
                confidence=0.0,
                engine="llm",
            )

        # Retourner le résultat mis en cache si le même texte a déjà été traduit
        # depuis le dernier reload(). Le cache est invalidé à chaque reload().
        cache_key = (text.strip(), source_language)
        cached = self._response_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            user_message = self._build_user_message(text, source_language)
            message = self._client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            translated = normalize_bassa(message.content[0].text.strip())

            dict_result = self._dict_engine.translate(text, source_language)

            result = TranslationResult(
                source_text=text,
                translated_text=translated,
                source_language=source_language,
                confidence=0.90,
                word_translations=dict_result.word_translations,
                warnings=[
                    f"Traduction générée par Claude ({settings.CLAUDE_MODEL}). "
                    "Vérification conseillée pour usage officiel."
                ],
                engine="llm-claude",
            )
            self._response_cache[cache_key] = result
            return result

        except Exception as exc:
            logger.error("Erreur API Claude : %s", exc)
            if self._fallback is not None:
                result = self._fallback.translate(text, source_language)
                result.warnings.insert(0, "Claude API indisponible — moteur de secours utilisé.")
                return result
            result = self._dict_engine.translate(text, source_language)
            result.warnings.insert(0, "Claude API indisponible — dictionnaire utilisé.")
            return result
