"""normalize.py — passe DataFrame brut -> DataFrame propre.

Apres `ingest.read_csv` on a :
    date (str), card (str), description (str), category (str),
    debit (float >= 0), credit (float >= 0)

On veut :
    date (datetime64[ns]), card (str), description (str), category (str),
    amount (float, signé : positif = dépense, négatif = remboursement),
    profile (str si fourni)

La déduplication est **désactivée par défaut** : deux transactions du même
jour avec la même description et le même montant sont des achats légitimes
(par exemple deux cafés à 5 minutes d'intervalle). On l'active seulement
quand on suspecte un import en double (`dedup=True`).
"""

from __future__ import annotations

import pandas as pd


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse robustement une colonne de dates (formats ISO, FR, mixtes)."""
    s = series.astype(str).str.strip()
    out = pd.to_datetime(s, format="%Y-%m-%d", errors="coerce")
    mask = out.isna()
    if mask.any():
        out2 = pd.to_datetime(s[mask], format="%d/%m/%Y", errors="coerce")
        out.loc[mask] = out2
        mask = out.isna()
    if mask.any():
        out3 = pd.to_datetime(s[mask], errors="coerce")
        out.loc[mask] = out3
    return out


def normalize(df: pd.DataFrame, profile: str | None = None, dedup: bool = False) -> pd.DataFrame:
    """Normalise un DataFrame issu de `ingest.read_csv`.

    - parse les dates
    - signe les montants (debit positif = dépense, credit négatif = remboursement)
    - retire les doublons exacts seulement si `dedup=True` (utile quand on
      réimporte le même fichier deux fois)
    """
    if df.empty:
        cols = ["date", "card", "description", "category", "amount"]
        if profile:
            cols.append("profile")
        return pd.DataFrame(columns=cols)

    out = df.copy()
    out["date"] = parse_dates(out["date"])

    debit = out["debit"].astype(float).fillna(0.0)
    credit = out["credit"].astype(float).fillna(0.0)
    out["amount"] = debit - credit

    out = out[["date", "card", "description", "category", "amount"]]
    out["description"] = out["description"].astype(str).str.strip()
    out["category"] = out["category"].astype(str).str.strip()

    if dedup:
        out = out.drop_duplicates(subset=["date", "card", "description", "amount"], keep="first")
    out = out.reset_index(drop=True)

    if profile:
        out["profile"] = profile

    return out
