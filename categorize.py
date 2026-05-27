"""categorize.py — catégorisation par règles + fallback LLM.

Beaucoup d'exports bancaires arrivent déjà catégorisés. Mais quand ce n'est
pas le cas (ou que la catégorie est vide), on applique :

1. Un dictionnaire de règles `keyword -> category`.
2. Si aucune règle ne matche, on délègue au LLM via une fonction passée en
   paramètre (qu'elle pointe vers Ollama, OpenAI, ou autre).

Les règles sont écrites en minuscules, le matching est case-insensitive et
sub-string : si `description.lower()` contient `keyword.lower()`, on prend
la catégorie.
"""

from __future__ import annotations

from typing import Callable, Iterable


# Catalogue de catégories de référence (les mêmes que dans data1-anonymized.csv).
KNOWN_CATEGORIES: list[str] = [
    "Cafés",
    "Restauration rapide",
    "Restaurants",
    "Épicerie",
    "Carburant et essence",
    "Stationnement",
    "Location d'auto et taxi",
    "Avion",
    "Hôtel",
    "Voyage",
    "Cellulaire",
    "Internet",
    "Cable",
    "Hébergement web",
    "Électroniques et logiciels",
    "Magasinage",
    "Vêtements",
    "Articles de sport",
    "Salle d'entraînement",
    "Sports",
    "Divertissement",
    "Salon de coiffure",
    "Pharmacie",
    "Docteur",
    "Optométriste",
    "Rénovations",
    "Éducation",
    "Publicité",
    "Mon entreprise",
    "Services",
    "Frais de livraison",
    "Frais",
    "Factures et services",
    "Finances",
    "Juridique",
    "Paiement carte de crédit",
    "Retrait en argent comptant",
    "Transfert",
    "Nourriture et boisson",
]


# Règles par défaut : keyword -> category (sub-string, case-insensitive).
DEFAULT_RULES: dict[str, str] = {
    # Cafés
    "coffee gossip": "Cafés",
    "bean atlas": "Cafés",
    "café aslan": "Cafés",
    "café pertama": "Cafés",
    "twin cup": "Cafés",
    "reindeer roast": "Cafés",
    "mocha maven": "Cafés",
    "espresso pod": "Cafés",
    # Restauration rapide / restaurants
    "burger atlas": "Restauration rapide",
    "spicy sahibi": "Restauration rapide",
    "campus plate": "Restauration rapide",
    "mango selera": "Restauration rapide",
    "sahabat tapas": "Restaurants",
    "boulanger": "Restauration rapide",
    "sedap eats": "Restauration rapide",
    "quickserve": "Restaurants",
    "manakish house": "Restaurants",
    "trattoria yildiz": "Restaurants",
    "pasha bistro": "Restaurants",
    "old harbor steakhouse": "Restaurants",
    # Épicerie
    "megamart": "Épicerie",
    "safe stop foods": "Épicerie",
    "pasar pagi": "Épicerie",
    "crossroads market": "Épicerie",
    "westend express": "Épicerie",
    # Carburant
    "maple fuel": "Carburant et essence",
    "wholesalefuel": "Carburant et essence",
    "speedy stop": "Carburant et essence",
    "night owl mart": "Carburant et essence",
    "desert oil": "Carburant et essence",
    # Stationnement
    "parkslot": "Stationnement",
    "bluelot": "Stationnement",
    "stanley park lot": "Stationnement",
    # Transport
    "ridehail": "Location d'auto et taxi",
    "city taxi": "Location d'auto et taxi",
    "hamza taxi": "Location d'auto et taxi",
    "maple airways": "Avion",
    "patriot airways": "Avion",
    "pearl aviation": "Avion",
    # Tech / abonnements
    "tahir ai": "Électroniques et logiciels",
    "perakai": "Électroniques et logiciels",
    "deployhub": "Hébergement web",
    "workspace one": "Électroniques et logiciels",
    "datamove transfer": "Électroniques et logiciels",
    "repohub": "Électroniques et logiciels",
    "texcloud": "Électroniques et logiciels",
    "designkit": "Électroniques et logiciels",
    "boardly": "Électroniques et logiciels",
    "memberkit": "Électroniques et logiciels",
    "payforge": "Électroniques et logiciels",
    "skillbay": "Éducation",
    "learnify": "Éducation",
    "techconf": "Éducation",
    # Streaming / divertissement
    "streamkite": "Divertissement",
    "clipstream": "Divertissement",
    "ticketwave": "Divertissement",
    # Telecom
    "fibrelynx": "Cable",
    "stellar plus": "Cellulaire",
    "stellar mobile": "Cellulaire",
    "munich hosting": "Hébergement web",
    # Magasinage
    "selangor mart": "Magasinage",
    "selangor prime": "Magasinage",
    "selangor cloud": "Hébergement web",
    "mega bazaar": "Magasinage",
    "northern hardware": "Magasinage",
    "pennymart": "Magasinage",
    "pasaron": "Magasinage",
    "champion outlet": "Magasinage",
    "sumber apparel": "Vêtements",
    "sportback studio": "Vêtements",
    "karahan garments": "Vêtements",
    "karahan boutique": "Vêtements",
    # Sport
    "flexfit": "Salle d'entraînement",
    # Salon
    "crown studio": "Salon de coiffure",
    # Health
    "medbonjour": "Docteur",
    "pharmaquik": "Pharmacie",
    "visionclear": "Optométriste",
    # Logement / Travel
    "diplomat suites": "Hôtel",
    "coral bay resort": "Hôtel",
    "tripscout": "Voyage",
    "guidemate": "Voyage",
    "compass tours": "Voyage",
    "backroute": "Voyage",
    # Misc
    "mavi tech": "Électroniques et logiciels",
    "mavi studio": "Électroniques et logiciels",
    "quickpay": "Frais",
    "storeville": "Magasinage",
    "stadium snacks": "Restauration rapide",
    "snack sultanate": "Restauration rapide",
    # Système
    "paiement reçu merci": "Paiement carte de crédit",
    "intérêts mastercard": "Finances",
    "programme remise en argent": "Transfert",
    "avance de fonds": "Retrait en argent comptant",
    "constat d'infraction": "Frais",
}


LlmCategorizer = Callable[[str, list[str]], str]
"""Fonction (description, candidates) -> categorie. Doit retourner une
chaîne dans `candidates` ou la chaîne vide si indéterminé."""


def categorize_one(
    description: str,
    existing_category: str = "",
    rules: dict[str, str] | None = None,
    llm: LlmCategorizer | None = None,
    candidates: Iterable[str] | None = None,
) -> str:
    """Détermine la catégorie d'une transaction.

    1. Si `existing_category` est non vide et connu, on le garde.
    2. Sinon, on cherche un keyword des `rules` dans `description` (case-insensitive).
    3. Sinon, si `llm` fourni, on demande au LLM de choisir parmi `candidates`.
    4. Sinon, on retourne la chaîne vide.
    """
    if existing_category and existing_category.strip():
        return existing_category.strip()
    rules = rules or DEFAULT_RULES
    desc_low = description.lower()
    for kw, cat in rules.items():
        if kw in desc_low:
            return cat
    if llm is not None:
        cand = list(candidates) if candidates else KNOWN_CATEGORIES
        try:
            return (llm(description, cand) or "").strip()
        except Exception:
            return ""
    return ""


def categorize_dataframe(
    df,
    rules: dict[str, str] | None = None,
    llm: LlmCategorizer | None = None,
    candidates: Iterable[str] | None = None,
):
    """Applique `categorize_one` ligne à ligne, écrit en place dans `df.category`."""
    df = df.copy()
    df["category"] = [
        categorize_one(
            description=row["description"],
            existing_category=row.get("category", ""),
            rules=rules,
            llm=llm,
            candidates=candidates,
        )
        for _, row in df.iterrows()
    ]
    return df
