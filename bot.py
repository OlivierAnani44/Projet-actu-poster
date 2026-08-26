"""Compatibilité avec l'ancien démarrage Railway ``python bot.py``.

Sous GitHub Actions, ce fichier publie une seule actualité football puis quitte.
La fréquence est définie dans le workflow YAML.
"""

from main import CONFIG
from news_publisher import run_cli


if __name__ == "__main__":
    run_cli(CONFIG)

