"""Maintenance commands.

Examples:
    python manage.py migrate
    python manage.py backup --output backups
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

from core.config import Settings
from core.database import Database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="Create or upgrade the database schema")
    backup = commands.add_parser("backup", help="Copy the database, vector index, and original documents")
    backup.add_argument("--output", type=Path, default=Path("backups"))

    args = parser.parse_args()
    settings = Settings.from_env()
    db = Database(settings.db_path)

    if args.command == "migrate":
        print(f"Database schema is at version {db.schema_version}.")
    elif args.command == "backup":
        target = args.output / datetime.now().strftime("backup-%Y%m%d-%H%M%S")
        db.backup_to(target / settings.db_path.name)
        if settings.store_path.exists():
            shutil.copy2(settings.store_path, target / settings.store_path.name)
        if settings.documents_dir.exists():
            shutil.copytree(settings.documents_dir, target / "documents")
        print(f"Backup written to {target}")


if __name__ == "__main__":
    main()
