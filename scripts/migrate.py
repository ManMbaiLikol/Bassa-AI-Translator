"""Utilitaire Alembic pour BassaAI Translator.

Usage (depuis la racine du projet) :

    # Voir l'état actuel
    python scripts/migrate.py status

    # Appliquer toutes les migrations en attente
    python scripts/migrate.py upgrade

    # Revenir d'une révision en arrière
    python scripts/migrate.py downgrade

    # Créer une nouvelle migration (autogenerate)
    python scripts/migrate.py make "description_courte"

    # Afficher l'historique des migrations
    python scripts/migrate.py history
"""
import sys
from pathlib import Path

# Ajouter la racine du projet au path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alembic.config import Config
from alembic import command


def get_alembic_cfg() -> Config:
    root = Path(__file__).resolve().parent.parent
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    return cfg


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    cfg = get_alembic_cfg()

    if cmd == "status":
        print("=== Révision actuelle ===")
        command.current(cfg, verbose=True)
        print("\n=== Migrations en attente ===")
        command.heads(cfg, verbose=True)

    elif cmd == "upgrade":
        target = args[1] if len(args) > 1 else "head"
        print(f"Mise à jour vers : {target}")
        command.upgrade(cfg, target)
        print("Migrations appliquées.")

    elif cmd == "downgrade":
        target = args[1] if len(args) > 1 else "-1"
        print(f"Retour à : {target}")
        command.downgrade(cfg, target)
        print("Rollback effectué.")

    elif cmd == "make":
        if len(args) < 2:
            print("Usage: python scripts/migrate.py make <description>")
            sys.exit(1)
        message = "_".join(args[1:])
        print(f"Génération de la migration : {message}")
        command.revision(cfg, autogenerate=True, message=message)

    elif cmd == "history":
        command.history(cfg, verbose=True)

    elif cmd == "stamp":
        target = args[1] if len(args) > 1 else "head"
        print(f"Marquage de la DB à : {target} (sans appliquer les migrations)")
        command.stamp(cfg, target)

    else:
        print(f"Commande inconnue : {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
