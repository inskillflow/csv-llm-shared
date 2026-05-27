"""csv_llm_shared — module partagé entre les apps csv-llm-ollama et csv-llm-openai.

Couches :
- ingest      : lecture CSV multi-banques -> DataFrame standardisé.
- normalize   : signature des montants, parsing des dates, dédup.
- db          : SQLite (init schéma, insert, query SELECT-only).
- categorize  : règles + fallback LLM pour catégoriser une transaction.
- dashboards  : fonctions Plotly prêtes à l'emploi.
- anonymize   : script CLI pour anonymiser un CSV à partir d'un YAML.
"""

__version__ = "0.1.0"
