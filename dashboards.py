"""dashboards.py — figures Plotly réutilisables.

Toutes les fonctions reçoivent un DataFrame normalisé contenant au moins :
    date (datetime), description (str), category (str), amount (float signé)

Convention `amount` :
    - positif  = dépense (on l'affiche tel quel)
    - négatif  = remboursement / crédit (on l'inverse pour les agrégats
      "dépenses", on le laisse pour les calculs nets)

Toutes les fonctions retournent un `plotly.graph_objects.Figure`.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _expenses_only(df: pd.DataFrame) -> pd.DataFrame:
    """Filtre les dépenses (amount > 0) — exclut crédits, remboursements, paiements."""
    if df.empty:
        return df
    return df[df["amount"] > 0].copy()


def kpi_totals(df: pd.DataFrame) -> dict[str, float]:
    """Trois métriques : dépense totale, dépense mensuelle moyenne, transaction moyenne."""
    exp = _expenses_only(df)
    if exp.empty:
        return {"total": 0.0, "monthly_avg": 0.0, "transaction_avg": 0.0, "n_transactions": 0}
    total = float(exp["amount"].sum())
    n = len(exp)
    months = (
        exp["date"].dt.to_period("M").nunique()
        if pd.api.types.is_datetime64_any_dtype(exp["date"])
        else 1
    )
    months = max(months, 1)
    return {
        "total": total,
        "monthly_avg": total / months,
        "transaction_avg": total / n if n else 0.0,
        "n_transactions": int(n),
    }


def fig_monthly(df: pd.DataFrame) -> go.Figure:
    """Histogramme des dépenses par mois (YYYY-MM)."""
    exp = _expenses_only(df)
    if exp.empty:
        return go.Figure().update_layout(title="Aucune dépense à afficher")
    monthly = (
        exp.assign(month=exp["date"].dt.to_period("M").astype(str))
           .groupby("month", as_index=False)["amount"]
           .sum()
           .sort_values("month")
    )
    fig = px.bar(monthly, x="month", y="amount",
                 labels={"month": "Mois", "amount": "Dépense ($)"},
                 title="Dépenses par mois")
    fig.update_traces(hovertemplate="%{x} : %{y:.2f} $<extra></extra>")
    return fig


def fig_by_category(df: pd.DataFrame) -> go.Figure:
    """Camembert (pie) des dépenses par catégorie."""
    exp = _expenses_only(df)
    if exp.empty:
        return go.Figure().update_layout(title="Aucune dépense à afficher")
    by_cat = (
        exp.groupby("category", as_index=False)["amount"]
           .sum()
           .sort_values("amount", ascending=False)
    )
    fig = px.pie(by_cat, values="amount", names="category",
                 title="Répartition par catégorie")
    fig.update_traces(textposition="inside", textinfo="percent+label",
                      hovertemplate="%{label} : %{value:.2f} $ (%{percent})<extra></extra>")
    return fig


def fig_top_merchants(df: pd.DataFrame, n: int = 10) -> go.Figure:
    """Barres horizontales des `n` plus gros marchands."""
    exp = _expenses_only(df)
    if exp.empty:
        return go.Figure().update_layout(title="Aucune dépense à afficher")
    top = (
        exp.groupby("description", as_index=False)["amount"]
           .sum()
           .sort_values("amount", ascending=False)
           .head(n)
    )
    fig = px.bar(top, x="amount", y="description", orientation="h",
                 labels={"description": "Marchand", "amount": "Total dépensé ($)"},
                 title=f"Top {n} marchands")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    fig.update_traces(hovertemplate="%{y} : %{x:.2f} $<extra></extra>")
    return fig


def fig_recurring(df: pd.DataFrame, min_count: int = 3) -> go.Figure:
    """Marchands récurrents : ceux apparaissant au moins `min_count` mois différents."""
    exp = _expenses_only(df)
    if exp.empty or not pd.api.types.is_datetime64_any_dtype(exp["date"]):
        return go.Figure().update_layout(title="Aucune dépense à afficher")
    grouped = (
        exp.assign(month=exp["date"].dt.to_period("M").astype(str))
           .groupby("description")
           .agg(months=("month", "nunique"), total=("amount", "sum"))
           .reset_index()
    )
    rec = grouped[grouped["months"] >= min_count].sort_values("total", ascending=False).head(20)
    if rec.empty:
        return go.Figure().update_layout(title="Aucun marchand récurrent")
    fig = px.bar(rec, x="total", y="description", orientation="h",
                 hover_data={"months": True},
                 labels={"description": "Marchand", "total": "Total dépensé ($)",
                         "months": "Nb mois actifs"},
                 title=f"Marchands récurrents (≥ {min_count} mois)")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig
