"""
run_agent.py — Lance l'Agent IA DevOps depuis la racine du projet.
Charge automatiquement le fichier .env si présent (développement local).
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from agent.main import main

if __name__ == "__main__":
    main()
