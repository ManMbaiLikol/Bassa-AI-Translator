"""Phase 1 translation engine: dictionary lookup + grammatical rules."""
import re
import unicodedata

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models.dictionary import DictionaryEntry
from backend.models.grammar import GrammaticalRule
from backend.engine.base import TranslationEngine, TranslationResult, WordTranslation
from backend.engine.tokenizer import tokenize
from backend.engine.rule_transform import apply_rules, apply_db_rules


# Mapping of standalone modifier diacritics to combining marks.
# Handles cases where diacritics were stored as separate characters
# before the base letter (e.g. ˜ + n instead of ñ).
_MODIFIER_TO_COMBINING = {
    "\u00B4": "\u0301",  # ´ ACUTE ACCENT -> combining acute
    "\u0060": "\u0300",  # ` GRAVE ACCENT -> combining grave
    "\u02C6": "\u0302",  # ˆ MODIFIER CIRCUMFLEX -> combining circumflex
    "\u02DC": "\u0303",  # ˜ SMALL TILDE -> combining tilde
    "\u00A8": "\u0308",  # ¨ DIAERESIS -> combining diaeresis
    "\u02C7": "\u030C",  # ˇ CARON -> combining caron
    "\u00B8": "\u0327",  # ¸ CEDILLA -> combining cedilla
}

# Build regex: match any modifier followed by a letter
_MOD_PATTERN = re.compile(
    "([" + re.escape("".join(_MODIFIER_TO_COMBINING.keys())) + r"])(\w)",
    re.UNICODE,
)


def normalize_bassa(text: str) -> str:
    """Normalize Bassa text for proper diacritics rendering.

    1. Convert standalone modifier diacritics placed before a letter
       into combining marks placed after the letter.
    2. Apply Unicode NFC normalization to produce precomposed characters
       (e.g. n + combining tilde -> ñ).
    """
    # Step 1: Fix standalone modifier + letter -> letter + combining mark
    def _fix(m: re.Match) -> str:
        modifier = m.group(1)
        letter = m.group(2)
        combining = _MODIFIER_TO_COMBINING[modifier]
        return letter + combining

    text = _MOD_PATTERN.sub(_fix, text)
    # Step 2: NFC normalization (e + combining acute -> é)
    return unicodedata.normalize("NFC", text)

# French conjugated forms -> infinitive (most common verbs)
FR_LEMMAS = {
    # aller
    "vais": "aller", "vas": "aller", "va": "aller", "allons": "aller",
    "allez": "aller", "vont": "aller", "allait": "aller", "irai": "aller",
    "ira": "aller", "iront": "aller", "allé": "aller",
    # partir
    "pars": "partir", "part": "partir", "partons": "partir",
    "partez": "partir", "partent": "partir", "parti": "partir",
    "partait": "partir", "partira": "partir", "partirai": "partir",
    # rester
    "reste": "rester", "restes": "rester", "restons": "rester",
    "restez": "rester", "restent": "rester", "resté": "rester",
    "restait": "rester", "restera": "rester",
    # être
    "suis": "être", "es": "être", "est": "être", "sommes": "être",
    "êtes": "être", "sont": "être", "était": "être", "étais": "être",
    "serai": "être", "sera": "être", "seront": "être",
    # avoir
    "ai": "avoir", "as": "avoir", "avons": "avoir", "avez": "avoir",
    "ont": "avoir", "avait": "avoir", "aurai": "avoir", "aura": "avoir",
    # faire
    "fais": "faire", "fait": "faire", "faisons": "faire",
    "faites": "faire", "font": "faire", "fera": "faire", "ferai": "faire",
    # manger
    "mange": "manger", "manges": "manger", "mangeons": "manger",
    "mangez": "manger", "mangent": "manger", "mangé": "manger",
    "mangeait": "manger", "mangeais": "manger",
    # boire
    "bois": "boire", "boit": "boire", "buvons": "boire",
    "buvez": "boire", "boivent": "boire", "bu": "boire",
    # dormir
    "dors": "dormir", "dort": "dormir", "dormons": "dormir",
    "dormez": "dormir", "dorment": "dormir", "dormi": "dormir",
    # venir
    "viens": "venir", "vient": "venir", "venons": "venir",
    "venez": "venir", "viennent": "venir", "venu": "venir",
    "venait": "venir", "viendra": "venir",
    # voir
    "vois": "voir", "voit": "voir", "voyons": "voir",
    "voyez": "voir", "voient": "voir", "vu": "voir",
    # parler
    "parle": "parler", "parles": "parler", "parlons": "parler",
    "parlez": "parler", "parlent": "parler", "parlé": "parler",
    # aimer
    "aime": "aimer", "aimes": "aimer", "aimons": "aimer",
    "aimez": "aimer", "aiment": "aimer", "aimé": "aimer",
    # dire
    "dis": "dire", "dit": "dire", "disons": "dire",
    "dites": "dire", "disent": "dire",
    # pouvoir
    "peux": "pouvoir", "peut": "pouvoir", "pouvons": "pouvoir",
    "pouvez": "pouvoir", "peuvent": "pouvoir",
    # vouloir
    "veux": "vouloir", "veut": "vouloir", "voulons": "vouloir",
    "voulez": "vouloir", "veulent": "vouloir",
    # savoir
    "sais": "savoir", "sait": "savoir", "savons": "savoir",
    "savez": "savoir", "savent": "savoir",
    # donner
    "donne": "donner", "donnes": "donner", "donnons": "donner",
    "donnez": "donner", "donnent": "donner", "donné": "donner",
    # prendre
    "prends": "prendre", "prend": "prendre", "prenons": "prendre",
    "prenez": "prendre", "prennent": "prendre", "pris": "prendre",
    # travailler
    "travaille": "travailler", "travailles": "travailler",
    "travaillons": "travailler", "travaillez": "travailler",
    "travaillent": "travailler", "travaillé": "travailler",
    # mourir
    "meurs": "mourir", "meurt": "mourir", "mourons": "mourir",
    "mourez": "mourir", "meurent": "mourir", "mort": "mourir", "mourra": "mourir",
    # courir
    "cours": "courir", "court": "courir", "courons": "courir",
    "courez": "courir", "courent": "courir", "couru": "courir",
    # chanter
    "chante": "chanter", "chantes": "chanter", "chantons": "chanter",
    "chantez": "chanter", "chantent": "chanter", "chanté": "chanter",
    # pleurer
    "pleure": "pleurer", "pleures": "pleurer", "pleurons": "pleurer",
    "pleurez": "pleurer", "pleurent": "pleurer", "pleuré": "pleurer",
    # danser
    "danse": "danser", "danses": "danser", "dansons": "danser",
    "dansez": "danser", "dansent": "danser", "dansé": "danser",
    # écrire
    "écris": "écrire", "écrit": "écrire", "écrivons": "écrire",
    "écrivez": "écrire", "écrivent": "écrire",
    # lire
    "lis": "lire", "lit": "lire", "lisons": "lire",
    "lisez": "lire", "lisent": "lire", "lu": "lire",
    # ouvrir
    "ouvre": "ouvrir", "ouvres": "ouvrir", "ouvrons": "ouvrir",
    "ouvrez": "ouvrir", "ouvrent": "ouvrir", "ouvert": "ouvrir",
    # fermer
    "ferme": "fermer", "fermes": "fermer", "fermons": "fermer",
    "fermez": "fermer", "ferment": "fermer", "fermé": "fermer",
    # couper
    "coupe": "couper", "coupes": "couper", "coupons": "couper",
    "coupez": "couper", "coupent": "couper", "coupé": "couper",
    # laver
    "lave": "laver", "laves": "laver", "lavons": "laver",
    "lavez": "laver", "lavent": "laver", "lavé": "laver",
    # acheter
    "achète": "acheter", "achètes": "acheter", "achetons": "acheter",
    "achetez": "acheter", "achètent": "acheter", "acheté": "acheter",
    # vendre
    "vends": "vendre", "vend": "vendre", "vendons": "vendre",
    "vendez": "vendre", "vendent": "vendre", "vendu": "vendre",
    # payer
    "paie": "payer", "paies": "payer", "payons": "payer",
    "payez": "payer", "paient": "payer", "payé": "payer",
    # chercher
    "cherche": "chercher", "cherches": "chercher", "cherchons": "chercher",
    "cherchez": "chercher", "cherchent": "chercher", "cherché": "chercher",
    # trouver
    "trouve": "trouver", "trouves": "trouver", "trouvons": "trouver",
    "trouvez": "trouver", "trouvent": "trouver", "trouvé": "trouver",
    # croire
    "crois": "croire", "croit": "croire", "croyons": "croire",
    "croyez": "croire", "croient": "croire", "cru": "croire",
    # penser
    "pense": "penser", "penses": "penser", "pensons": "penser",
    "pensez": "penser", "pensent": "penser", "pensé": "penser",
    # aider
    "aide": "aider", "aides": "aider", "aidons": "aider",
    "aidez": "aider", "aident": "aider", "aidé": "aider",
    # demander
    "demande": "demander", "demandes": "demander", "demandons": "demander",
    "demandez": "demander", "demandent": "demander", "demandé": "demander",
    # répondre
    "réponds": "répondre", "répond": "répondre", "répondons": "répondre",
    "répondez": "répondre", "répondent": "répondre", "répondu": "répondre",
    # cuisiner
    "cuisine": "cuisiner", "cuisines": "cuisiner", "cuisinons": "cuisiner",
    "cuisinez": "cuisiner", "cuisinent": "cuisiner", "cuisiné": "cuisiner",
    # tuer
    "tue": "tuer", "tues": "tuer", "tuons": "tuer",
    "tuez": "tuer", "tuent": "tuer", "tué": "tuer",
    # vivre
    "vis": "vivre", "vit": "vivre", "vivons": "vivre",
    "vivez": "vivre", "vivent": "vivre", "vécu": "vivre",
    # tomber
    "tombe": "tomber", "tombes": "tomber", "tombons": "tomber",
    "tombez": "tomber", "tombent": "tomber", "tombé": "tomber",
    # commencer
    "commence": "commencer", "commences": "commencer",
    "commençons": "commencer", "commencez": "commencer",
    "commencent": "commencer", "commencé": "commencer",
    # finir
    "finis": "finir", "finit": "finir", "finissons": "finir",
    "finissez": "finir", "finissent": "finir", "fini": "finir",
    # apprendre
    "apprends": "apprendre", "apprend": "apprendre", "apprenons": "apprendre",
    "apprenez": "apprendre", "apprennent": "apprendre", "appris": "apprendre",
    # enseigner
    "enseigne": "enseigner", "enseignes": "enseigner", "enseignons": "enseigner",
    "enseignez": "enseigner", "enseignent": "enseigner", "enseigné": "enseigner",
    # jouer
    "joue": "jouer", "joues": "jouer", "jouons": "jouer",
    "jouez": "jouer", "jouent": "jouer", "joué": "jouer",
    # prier
    "prie": "prier", "pries": "prier", "prions": "prier",
    "priez": "prier", "prient": "prier", "prié": "prier",
    # envoyer
    "envoie": "envoyer", "envoies": "envoyer", "envoyons": "envoyer",
    "envoyez": "envoyer", "envoient": "envoyer", "envoyé": "envoyer",
    # construire
    "construis": "construire", "construit": "construire",
    "construisons": "construire", "construisez": "construire",
    "construisent": "construire",
    # marcher
    "marche": "marcher", "marches": "marcher", "marchons": "marcher",
    "marchez": "marcher", "marchent": "marcher", "marché": "marcher",
    # appeler
    "appelle": "appeler", "appelles": "appeler", "appelons": "appeler",
    "appelez": "appeler", "appellent": "appeler", "appelé": "appeler",
    # écouter
    "écoute": "écouter", "écoutes": "écouter", "écoutons": "écouter",
    "écoutez": "écouter", "écoutent": "écouter", "écouté": "écouter",
    # entendre
    "entends": "entendre", "entend": "entendre", "entendons": "entendre",
    "entendez": "entendre", "entendent": "entendre", "entendu": "entendre",
    # regarder
    "regarde": "regarder", "regardes": "regarder", "regardons": "regarder",
    "regardez": "regarder", "regardent": "regarder", "regardé": "regarder",
    # oublier
    "oublie": "oublier", "oublies": "oublier", "oublions": "oublier",
    "oubliez": "oublier", "oublient": "oublier", "oublié": "oublier",
    # laisser
    "laisse": "laisser", "laisses": "laisser", "laissons": "laisser",
    "laissez": "laisser", "laissent": "laisser", "laissé": "laisser",
    # frapper
    "frappe": "frapper", "frappes": "frapper", "frappons": "frapper",
    "frappez": "frapper", "frappent": "frapper", "frappé": "frapper",
    # crier
    "crie": "crier", "cries": "crier", "crions": "crier",
    "criez": "crier", "crient": "crier", "crié": "crier",
    # voler
    "vole": "voler", "voles": "voler", "volons": "voler",
    "volez": "voler", "volent": "voler", "volé": "voler",
    # brûler
    "brûle": "brûler", "brûles": "brûler", "brûlons": "brûler",
    "brûlez": "brûler", "brûlent": "brûler", "brûlé": "brûler",
    # naître
    "nais": "naître", "naît": "naître", "naissons": "naître",
    "naissez": "naître", "naissent": "naître", "né": "naître",
    # montrer
    "montre": "montrer", "montres": "montrer", "montrons": "montrer",
    "montrez": "montrer", "montrent": "montrer", "montré": "montrer",
}

# English conjugated forms -> base form
EN_LEMMAS = {
    # go
    "goes": "go", "going": "go", "went": "go", "gone": "go",
    # eat
    "eats": "eat", "eating": "eat", "ate": "eat", "eaten": "eat",
    # drink
    "drinks": "drink", "drinking": "drink", "drank": "drink", "drunk": "drink",
    # sleep
    "sleeps": "sleep", "sleeping": "sleep", "slept": "sleep",
    # come
    "comes": "come", "coming": "come", "came": "come",
    # see
    "sees": "see", "seeing": "see", "saw": "see", "seen": "see",
    # speak
    "speaks": "speak", "speaking": "speak", "spoke": "speak", "spoken": "speak",
    # love
    "loves": "love", "loving": "love", "loved": "love",
    # give
    "gives": "give", "giving": "give", "gave": "give", "given": "give",
    # take
    "takes": "take", "taking": "take", "took": "take", "taken": "take",
    # work
    "works": "work", "working": "work", "worked": "work",
    # do/make
    "does": "do", "doing": "do", "did": "do", "done": "do",
    "makes": "make", "making": "make", "made": "make",
    # say/tell
    "says": "say", "saying": "say", "said": "say",
    "tells": "tell", "telling": "tell", "told": "tell",
    # know
    "knows": "know", "knowing": "know", "knew": "know", "known": "know",
    # want
    "wants": "want", "wanting": "want", "wanted": "want",
    # die
    "dies": "die", "dying": "die", "died": "die", "dead": "die",
    # live
    "lives": "live", "living": "live", "lived": "live",
    # run
    "runs": "run", "running": "run", "ran": "run",
    # walk
    "walks": "walk", "walking": "walk", "walked": "walk",
    # dance
    "dances": "dance", "dancing": "dance", "danced": "dance",
    # sing
    "sings": "sing", "singing": "sing", "sang": "sing", "sung": "sing",
    # cry
    "cries": "cry", "crying": "cry", "cried": "cry",
    # laugh
    "laughs": "laugh", "laughing": "laugh", "laughed": "laugh",
    # hear/listen
    "hears": "hear", "hearing": "hear", "heard": "hear",
    "listens": "listen", "listening": "listen", "listened": "listen",
    # look
    "looks": "look", "looking": "look", "looked": "look",
    # think
    "thinks": "think", "thinking": "think", "thought": "think",
    # believe
    "believes": "believe", "believing": "believe", "believed": "believe",
    # wait
    "waits": "wait", "waiting": "wait", "waited": "wait",
    # open/close
    "opens": "open", "opening": "open", "opened": "open",
    "closes": "close", "closing": "close", "closed": "close",
    # wash
    "washes": "wash", "washing": "wash", "washed": "wash",
    # cut
    "cuts": "cut", "cutting": "cut",
    # build
    "builds": "build", "building": "build", "built": "build",
    # burn
    "burns": "burn", "burning": "burn", "burned": "burn", "burnt": "burn",
    # cook
    "cooks": "cook", "cooking": "cook", "cooked": "cook",
    # buy/sell/pay
    "buys": "buy", "buying": "buy", "bought": "buy",
    "sells": "sell", "selling": "sell", "sold": "sell",
    "pays": "pay", "paying": "pay", "paid": "pay",
    # read/write
    "reads": "read", "reading": "read",
    "writes": "write", "writing": "write", "wrote": "write", "written": "write",
    # learn/teach
    "learns": "learn", "learning": "learn", "learned": "learn", "learnt": "learn",
    "teaches": "teach", "teaching": "teach", "taught": "teach",
    # play
    "plays": "play", "playing": "play", "played": "play",
    # pray
    "prays": "pray", "praying": "pray", "prayed": "pray",
    # help
    "helps": "help", "helping": "help", "helped": "help",
    # ask/answer
    "asks": "ask", "asking": "ask", "asked": "ask",
    "answers": "answer", "answering": "answer", "answered": "answer",
    # fight/kill/steal
    "fights": "fight", "fighting": "fight", "fought": "fight",
    "kills": "kill", "killing": "kill", "killed": "kill",
    "steals": "steal", "stealing": "steal", "stole": "steal", "stolen": "steal",
    # fall
    "falls": "fall", "falling": "fall", "fell": "fall", "fallen": "fall",
    # send/show
    "sends": "send", "sending": "send", "sent": "send",
    "shows": "show", "showing": "show", "showed": "show", "shown": "show",
    # call/hit/leave
    "calls": "call", "calling": "call", "called": "call",
    "hits": "hit", "hitting": "hit",
    "leaves": "leave", "leaving": "leave", "left": "leave",
    # forget/begin/finish
    "forgets": "forget", "forgetting": "forget", "forgot": "forget", "forgotten": "forget",
    "begins": "begin", "beginning": "begin", "began": "begin", "begun": "begin",
    "finishes": "finish", "finishing": "finish", "finished": "finish",
    # have/be
    "has": "have", "having": "have", "had": "have",
    # count
    "counts": "count", "counting": "count", "counted": "count",
    # touch
    "touches": "touch", "touching": "touch", "touched": "touch",
    # break
    "breaks": "break", "breaking": "break", "broke": "break", "broken": "break",
    # irregular plurals
    "children": "child", "men": "man", "women": "woman",
    "teeth": "tooth", "feet": "foot", "eyes": "eye",
    "people": "person",
}


class DictionaryEngine(TranslationEngine):
    def __init__(self):
        self._cache: dict[str, dict[str, str]] = {}  # {lang: {word: bassa_word}}
        self._multi_word: dict[str, dict[str, str]] = {}  # {lang: {multi_word: bassa}}
        self._db_rules: list[dict] = []  # règles GrammaticalRule actives depuis la DB
        self.reload()

    def reload(self, db: Session = None) -> None:
        """Load dictionary entries into memory.

        If *db* is provided, that session is used (and NOT closed) — this
        ensures we see data committed in the caller's transaction.  When *db*
        is None a fresh SessionLocal is created and closed internally.
        """
        self._cache = {"fr": {}, "en": {}}
        self._multi_word = {"fr": {}, "en": {}}
        own_session = db is None
        if own_session:
            db = SessionLocal()
        try:
            entries = db.query(DictionaryEntry).order_by(DictionaryEntry.is_verified.asc()).all()
            for entry in entries:
                lang = entry.source_language
                word = entry.source_word.lower()
                bassa = normalize_bassa(entry.bassa_word)
                if lang not in self._cache:
                    self._cache[lang] = {}
                    self._multi_word[lang] = {}
                if " " in word:
                    self._multi_word[lang][word] = bassa
                else:
                    self._cache[lang][word] = bassa
            self._db_rules = [
                {
                    "source_language": r.source_language,
                    "rule_name": r.rule_name,
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

    def _lookup(self, word: str, language: str) -> str | None:
        w = word.lower()
        cache = self._cache.get(language, {})
        # Direct lookup
        result = cache.get(w)
        if result:
            return result
        # Lemmatization fallback: try the base/infinitive form
        lemmas = FR_LEMMAS if language == "fr" else EN_LEMMAS
        base_form = lemmas.get(w)
        if base_form:
            result = cache.get(base_form)
            if result:
                return result
        # Morphological fallback: try stripping common suffixes
        candidates = self._strip_morphology(w, language)
        for c in candidates:
            result = cache.get(c)
            if result:
                return result
        return None

    @staticmethod
    def _strip_morphology(word: str, language: str) -> list[str]:
        """Generate candidate base forms by stripping common suffixes."""
        candidates = []
        if language == "fr":
            # French plural: -s, -x, -aux -> -al
            if word.endswith("aux") and len(word) > 4:
                candidates.append(word[:-3] + "al")  # animaux -> animal
            if word.endswith("s") and len(word) > 2:
                candidates.append(word[:-1])  # enfants -> enfant
            if word.endswith("x") and len(word) > 2:
                candidates.append(word[:-1])  # cheveux -> cheveu
            # French feminine: -e
            if word.endswith("e") and len(word) > 3:
                candidates.append(word[:-1])  # grande -> grand
            if word.endswith("se") and len(word) > 4:
                candidates.append(word[:-2] + "x")  # heureuse -> heureux
            if word.endswith("ère") and len(word) > 4:
                candidates.append(word[:-3] + "er")  # première -> premier
        else:
            # English plural: -s, -es, -ies -> -y
            if word.endswith("ies") and len(word) > 4:
                candidates.append(word[:-3] + "y")  # stories -> story
            if word.endswith("ves") and len(word) > 4:
                candidates.append(word[:-3] + "fe")  # wives -> wife
            if word.endswith("es") and len(word) > 3:
                candidates.append(word[:-2])  # churches -> church
            if word.endswith("s") and len(word) > 2:
                candidates.append(word[:-1])  # dogs -> dog
            # English -ly -> adjective
            if word.endswith("ly") and len(word) > 4:
                candidates.append(word[:-2])  # quickly -> quick
        return candidates

    def translate(self, text: str, source_language: str) -> TranslationResult:
        if not text.strip():
            return TranslationResult(
                source_text=text, translated_text="", source_language=source_language,
                confidence=0.0, engine="dictionary",
            )

        # Step 1: Check for full-text match in multi-word entries
        text_lower = text.lower().strip()
        multi_match = self._multi_word.get(source_language, {}).get(text_lower)
        if multi_match:
            return TranslationResult(
                source_text=text,
                translated_text=multi_match,
                source_language=source_language,
                confidence=1.0,
                word_translations=[WordTranslation(source=text_lower, translated=multi_match, found=True)],
                engine="dictionary",
            )

        # Step 2: Tokenize
        tokens = tokenize(text, source_language)
        if not tokens:
            return TranslationResult(
                source_text=text, translated_text=text, source_language=source_language,
                confidence=0.0, warnings=["No tokens found"], engine="dictionary",
            )

        # Step 3: Multi-word lookup (greedy, longest match first)
        word_results = []
        i = 0
        while i < len(tokens):
            matched = False
            # Try longest multi-word match first (up to 4 tokens)
            for length in range(min(4, len(tokens) - i), 1, -1):
                phrase = " ".join(tokens[i:i + length])
                multi = self._multi_word.get(source_language, {}).get(phrase)
                if multi:
                    word_results.append({"source": phrase, "translated": multi, "found": True})
                    i += length
                    matched = True
                    break
            if not matched:
                # Single word lookup
                bassa = self._lookup(tokens[i], source_language)
                word_results.append({
                    "source": tokens[i],
                    "translated": bassa if bassa else tokens[i],
                    "found": bassa is not None,
                })
                i += 1

        # Step 4a: Apply DB grammatical rules (admin-defined, token-level regex)
        lang_db_rules = [r for r in self._db_rules if r["source_language"] == source_language]
        if lang_db_rules:
            word_results = apply_db_rules(word_results, lang_db_rules)

        # Step 4b: Apply hardcoded grammatical rules (articles, prepositions, negation)
        transformed = apply_rules(tokens, word_results, source_language)

        # Step 5: Build result
        translated_words = [t["translated"] for t in transformed]
        translated_text = normalize_bassa(" ".join(translated_words))

        # Confidence scoring: don't penalize articles/prepositions removed by rules
        grammar_words_fr = {"le", "la", "les", "un", "une", "des", "du", "de", "à", "l", "d"}
        grammar_words_en = {"the", "a", "an", "is", "are", "was", "were", "do", "does", "did",
                            "am", "of", "to", "at"}
        grammar_words = grammar_words_fr if source_language == "fr" else grammar_words_en
        content_words = [w for w in word_results if w["source"] not in grammar_words]
        total = len(content_words)
        found = sum(1 for w in content_words if w["found"])
        confidence = found / total if total > 0 else 0.0

        warnings = []
        not_found = [w["source"] for w in word_results
                     if not w["found"] and w["source"] not in grammar_words]
        if not_found:
            warnings.append(f"Words not in dictionary: {', '.join(not_found)}")

        word_translations = [
            WordTranslation(source=w["source"], translated=w["translated"], found=w["found"])
            for w in word_results
        ]

        return TranslationResult(
            source_text=text,
            translated_text=translated_text,
            source_language=source_language,
            confidence=round(confidence, 2),
            word_translations=word_translations,
            warnings=warnings,
            engine="dictionary",
        )
