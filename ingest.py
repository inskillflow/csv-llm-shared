"""ingest.py — lecture multi-format de fichiers CSV de carte de crédit.

Le format `data1-anonymized.csv` est :
    Date;Numéro de Carte;Description;Catégorie;Debit;Credit
    2027-12-27;************4382;Late Payment Fee;Fees;24.31;0

Mais les exports bancaires varient :
- séparateur `;` ou `,`
- BOM UTF-8 ou non
- noms de colonnes en français OU en anglais
- une colonne `Amount` signée OU deux colonnes `Debit` / `Credit`

Cette couche standardise tout ça vers un DataFrame avec les colonnes :
    date            : datetime64[ns]
    card            : str (numéro de carte masqué)
    description     : str (libellé du marchand)
    category        : str ('' si inconnu)
    debit           : float (>= 0, montant débité)
    credit          : float (>= 0, montant crédité)
    profile         : str (ajouté par l'appelant)
"""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path
from typing import IO, Iterable

import pandas as pd


# Mapping des en-têtes possibles -> nom canonique
HEADER_ALIASES: dict[str, str] = {
    # date
    "date": "date",
    "transaction date": "date",
    "posted date": "date",
    "post date": "date",
    "date de transaction": "date",
    # carte
    "numéro de carte": "card",
    "numero de carte": "card",
    "card number": "card",
    "card": "card",
    "carte": "card",
    # description
    "description": "description",
    "merchant": "description",
    "merchant name": "description",
    "marchand": "description",
    "libellé": "description",
    "libelle": "description",
    # catégorie
    "catégorie": "category",
    "categorie": "category",
    "category": "category",
    # montants
    "debit": "debit",
    "débit": "debit",
    "credit": "credit",
    "crédit": "credit",
    "amount": "amount",
    "montant": "amount",
}


def _detect_delimiter(sample: str) -> str:
    """Detecte le separateur (`;` ou `,`) sur un echantillon de la 1re ligne."""
    if sample.count(";") > sample.count(","):
        return ";"
    return ","


def _normalize_header(h: str) -> str:
    return HEADER_ALIASES.get(h.strip().lower(), h.strip().lower())


def _parse_amount(value: str | float | int | None) -> float:
    """Parse un montant qui peut etre vide, '0', '12.34' ou '12,34'."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    s = s.replace(",", ".").replace(" ", "").replace("\xa0", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def read_csv(source: str | Path | IO[str]) -> pd.DataFrame:
    """Lit un CSV (chemin ou file-like) et retourne un DataFrame standardise.

    Accepte :
    - separateur `;` ou `,`
    - en-tetes francais ou anglais
    - une colonne `Amount` signee OU deux colonnes `Debit`/`Credit`
    - encodage UTF-8 (avec ou sans BOM)
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        text = path.read_text(encoding="utf-8-sig")
    else:
        # streamlit UploadedFile, etc. : on s'attend a du texte
        data = source.read()
        if isinstance(data, bytes):
            data = data.decode("utf-8-sig")
        text = data

    first_line = text.splitlines()[0] if text else ""
    delim = _detect_delimiter(first_line)

    reader = csv.reader(StringIO(text), delimiter=delim, quotechar='"')
    rows = list(reader)
    if not rows:
        return pd.DataFrame(columns=["date", "card", "description", "category", "debit", "credit"])

    raw_header = rows[0]
    header = [_normalize_header(h) for h in raw_header]
    body = rows[1:]

    df = pd.DataFrame(body, columns=header)

    # garantir les colonnes manquantes
    for col in ("date", "card", "description", "category"):
        if col not in df.columns:
            df[col] = ""

    if "debit" not in df.columns and "credit" not in df.columns and "amount" in df.columns:
        # Format mono-colonne : amount > 0 = depense, amount < 0 = remboursement
        df["amount"] = df["amount"].apply(_parse_amount)
        df["debit"] = df["amount"].clip(lower=0)
        df["credit"] = (-df["amount"]).clip(lower=0)
    else:
        df["debit"] = df.get("debit", 0).apply(_parse_amount)
        df["credit"] = df.get("credit", 0).apply(_parse_amount)

    df = df[["date", "card", "description", "category", "debit", "credit"]]

    # nettoyage simple
    for col in ("card", "description", "category"):
        df[col] = df[col].astype(str).str.strip()

    return df


def read_many(sources: Iterable[str | Path], profile: str | None = None) -> pd.DataFrame:
    """Lit plusieurs CSV et les concatene en un seul DataFrame."""
    frames = []
    for s in sources:
        df = read_csv(s)
        if profile:
            df["profile"] = profile
        frames.append(df)
    if not frames:
        cols = ["date", "card", "description", "category", "debit", "credit"]
        if profile:
            cols.append("profile")
        return pd.DataFrame(columns=cols)
    return pd.concat(frames, ignore_index=True)
