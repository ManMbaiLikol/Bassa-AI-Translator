# BassaAI Translator — Traducteur ɓàsàa

> Préservons et transmettons la langue du peuple Bàsàa du Cameroun grâce à l'intelligence artificielle.

🌐 **[Voir la page du projet](https://manmbailikol.github.io/Bassa-AI-Translator/)**

---

## Présentation

Application de traduction **Français / Anglais / Allemand ↔ Bàsàa** combinant trois moteurs complémentaires :

| Moteur | Description |
|--------|-------------|
| **Dictionnaire** | 41 357 entrées issues de sources linguistiques multiples |
| **ML (MiniLM)** | Modèle multilingue entraîné sur le corpus Bàsàa |
| **LLM (Claude)** | IA générative Anthropic pour les phrases complexes |

---

## Stack technique

- **Backend** : Python 3.13 · FastAPI · SQLAlchemy · MySQL
- **Frontend** : HTML/CSS · Alpine.js
- **Auth** : JWT · Google OAuth
- **Déploiement** : Docker · docker-compose

---

## Installation locale

```bash
# Cloner le dépôt
git clone https://github.com/ManMbaiLikol/Bassa-AI-Translator.git
cd Bassa-AI-Translator

# Configurer l'environnement
cp .env.example .env
# Éditer .env avec vos clés (DATABASE_URL, SECRET_KEY, ANTHROPIC_API_KEY...)

# Installer les dépendances
pip install -r requirements.txt

# Initialiser la base de données
python scripts/init_db.py

# Lancer le serveur
python scripts/run_dev.py
```

L'application est accessible sur `http://localhost:8000`.

---

## Lancer avec Docker

```bash
docker-compose up --build
```

---

## Tests

```bash
pytest tests/
```

---

## Structure du projet

```
Bassa-AI-Translator/
├── backend/
│   ├── api/          # Endpoints FastAPI
│   ├── engine/       # Moteurs de traduction (dict / ml / llm)
│   ├── models/       # Modèles SQLAlchemy
│   ├── schemas/      # Schémas Pydantic
│   └── seed/         # Données initiales du dictionnaire
├── frontend/         # Interface HTML / Alpine.js
├── scripts/          # Scripts d'initialisation et d'enrichissement
├── tests/            # Suite de tests pytest
├── alembic/          # Migrations de base de données
└── docs/             # Page GitHub Pages
```

---

## Contribuer

Les contributions sont les bienvenues ! Vous pouvez :

- Proposer de nouvelles entrées de dictionnaire via l'interface
- Signaler des erreurs de traduction dans les [Issues](https://github.com/ManMbaiLikol/Bassa-AI-Translator/issues)
- Soumettre une Pull Request

---

*Fait avec ❤️ pour le peuple Bàsàa du Cameroun*
