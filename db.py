"""db.py — couche SQLite pour les transactions.

Schéma :
    transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,                -- ISO `YYYY-MM-DD`
        card TEXT,
        description TEXT,
        category TEXT,
        amount REAL,              -- signé (positif = dépense, négatif = remboursement)
        profile TEXT
    )

Garde-fou : `safe_query` rejette tout SQL qui n'est pas un `SELECT` (pas
de DDL, pas de DML, pas de PRAGMA, pas d'ATTACH).

Utilisation :
    db.init("transactions.sqlite")
    db.insert_dataframe(df, profile="carte-perso")
    df = db.safe_query("SELECT category, SUM(amount) FROM transactions GROUP BY category")
"""

from __future__ import annotations

import re
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd


SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    card TEXT,
    description TEXT,
    category TEXT,
    amount REAL,
    profile TEXT
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_profile ON transactions(profile);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
"""


_SAFE_SELECT = re.compile(r"^\s*select\b", re.IGNORECASE | re.DOTALL)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum)\b",
    re.IGNORECASE,
)


def connect(path: str | Path) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec parser des dates ISO."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init(path: str | Path) -> None:
    """Crée le schéma si nécessaire."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as conn, conn:
        conn.executescript(SCHEMA)


def reset(path: str | Path, profile: str | None = None) -> int:
    """Supprime tout (ou seulement un profil). Retourne le nb de lignes supprimées."""
    with closing(connect(path)) as conn, conn:
        if profile is None:
            cur = conn.execute("DELETE FROM transactions")
        else:
            cur = conn.execute("DELETE FROM transactions WHERE profile = ?", (profile,))
        return cur.rowcount


def insert_dataframe(df: pd.DataFrame, path: str | Path, profile: str | None = None) -> int:
    """Insère un DataFrame normalisé. Retourne le nombre de lignes insérées."""
    if df.empty:
        return 0
    rows = []
    for _, r in df.iterrows():
        date = r.get("date")
        if pd.isna(date):
            continue
        date_str = pd.Timestamp(date).strftime("%Y-%m-%d")
        rows.append(
            (
                date_str,
                str(r.get("card", "")),
                str(r.get("description", "")),
                str(r.get("category", "")),
                float(r.get("amount", 0.0)),
                profile or r.get("profile") or "",
            )
        )
    with closing(connect(path)) as conn, conn:
        conn.executemany(
            "INSERT INTO transactions (date, card, description, category, amount, profile) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
    return len(rows)


def list_profiles(path: str | Path) -> list[str]:
    with closing(connect(path)) as conn:
        cur = conn.execute(
            "SELECT DISTINCT profile FROM transactions WHERE profile IS NOT NULL "
            "AND profile != '' ORDER BY profile"
        )
        return [r[0] for r in cur.fetchall()]


def count_rows(path: str | Path, profile: str | None = None) -> int:
    with closing(connect(path)) as conn:
        if profile:
            cur = conn.execute("SELECT COUNT(*) FROM transactions WHERE profile = ?", (profile,))
        else:
            cur = conn.execute("SELECT COUNT(*) FROM transactions")
        return int(cur.fetchone()[0])


def is_safe_select(sql: str) -> tuple[bool, str]:
    """Verifie qu'un SQL est un SELECT lecture seule.

    Retourne (ok, raison_si_pas_ok).
    """
    if not _SAFE_SELECT.match(sql):
        return False, "seuls les SELECT sont autorisés"
    if _FORBIDDEN.search(sql):
        return False, "mots-clés interdits détectés (insert/update/delete/drop/alter/create/attach/pragma/replace/vacuum)"
    if ";" in sql.strip().rstrip(";"):
        return False, "une seule requête à la fois (pas de `;` au milieu)"
    return True, ""


def safe_query(sql: str, path: str | Path, *, max_rows: int = 1000) -> pd.DataFrame:
    """Exécute un SELECT en lecture seule. Lève ValueError si le SQL est rejeté.

    `max_rows` borne le nombre de lignes retournées (anti-DoS).
    """
    ok, reason = is_safe_select(sql)
    if not ok:
        raise ValueError(f"SQL refusé : {reason}")
    with closing(connect(path)) as conn:
        df = pd.read_sql_query(sql, conn)
    if len(df) > max_rows:
        df = df.head(max_rows)
    return df


def fetch_all(path: str | Path, profile: str | None = None) -> pd.DataFrame:
    """Charge toutes les transactions (filtre optionnel par profil) en DataFrame."""
    with closing(connect(path)) as conn:
        if profile:
            df = pd.read_sql_query(
                "SELECT date, card, description, category, amount, profile "
                "FROM transactions WHERE profile = ? ORDER BY date",
                conn,
                params=(profile,),
            )
        else:
            df = pd.read_sql_query(
                "SELECT date, card, description, category, amount, profile "
                "FROM transactions ORDER BY date",
                conn,
            )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df
