"""smoke_pipeline.py — vérifie le pipeline ingest -> normalize -> SQLite.

Utilisé par verify.ps1. Lever AssertionError si quelque chose ne va pas.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # csv-llm-shared/
SIBLINGS = HERE.parent                          # 00-dream/  (parent commun aux repos)
sys.path.insert(0, str(HERE))

import db
import ingest
import normalize


def _resolve_csv() -> Path:
    """Trouve data1-anonymized.csv : variable d'env, sibling repo, ou local."""
    if env := os.environ.get("CSV_PATH"):
        return Path(env)
    candidates = [
        SIBLINGS / "ollama-streamlit" / "site" / "data" / "data1-anonymized.csv",
        HERE / "data" / "data1-anonymized.csv",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]  # pour message d'erreur explicite


def main() -> int:
    csv_path = _resolve_csv()
    db_path = HERE / ".cache" / "verify.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    df_raw = ingest.read_csv(csv_path)
    df = normalize.normalize(df_raw, profile="verify")
    db.init(db_path)
    n = db.insert_dataframe(df, db_path, profile="verify")

    assert n == 733, f"Attendu 733 lignes, obtenu {n}"

    total_df = db.safe_query(
        "SELECT ROUND(SUM(amount), 2) AS s FROM transactions WHERE amount > 0",
        db_path,
    )
    total = float(total_df.iloc[0]["s"])
    print(f"Lignes en DB : {n}")
    print(f"Total dépenses (amount>0) : {total} $")
    assert abs(total - 43567.04) < 0.01, f"Total dépense inattendu : {total}"

    cg_df = db.safe_query(
        "SELECT COUNT(*) AS n FROM transactions WHERE description = 'Coffee Gossip'",
        db_path,
    )
    cg = int(cg_df.iloc[0]["n"])
    print(f"Coffee Gossip : {cg} occurrences")
    assert cg == 106, f"Attendu 106, obtenu {cg}"

    cats_df = db.safe_query(
        "SELECT COUNT(DISTINCT category) AS n FROM transactions",
        db_path,
    )
    n_cats = int(cats_df.iloc[0]["n"])
    print(f"Catégories distinctes : {n_cats}")
    assert n_cats >= 30, f"Trop peu de catégories : {n_cats}"

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
