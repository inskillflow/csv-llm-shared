"""categorize.py — categorisation rules with optional LLM fallback.

Bank exports often already include categories. When the category is missing,
we first apply deterministic keyword rules, then optionally ask an LLM function
provided by the caller.
"""

from __future__ import annotations

from typing import Callable, Iterable


# Reference categories used by data1-anonymized.csv.
KNOWN_CATEGORIES: list[str] = [
    "Business",
    "Dining",
    "Education",
    "Entertainment",
    "Fees",
    "Groceries",
    "Health",
    "Housing",
    "Payments",
    "Refunds",
    "Transport",
    "Travel",
    "Utilities",
]


# Default rules: keyword -> category (sub-string, case-insensitive).
DEFAULT_RULES: dict[str, str] = {
    "fresh market": "Groceries",
    "pantry": "Groceries",
    "basket foods": "Groceries",
    "grocers": "Groceries",
    "family foods": "Groceries",
    "supermart": "Groceries",
    "organic store": "Groceries",
    "daily market": "Groceries",
    "bistro": "Dining",
    "cafe": "Dining",
    "noodle": "Dining",
    "sandwich": "Dining",
    "burger": "Dining",
    "curry": "Dining",
    "pizza": "Dining",
    "coffee room": "Dining",
    "transit": "Transport",
    "metro pass": "Transport",
    "cab": "Transport",
    "ferry": "Transport",
    "shuttle": "Transport",
    "parking": "Transport",
    "bus card": "Transport",
    "fuel stop": "Transport",
    "water services": "Utilities",
    "power": "Utilities",
    "fibre": "Utilities",
    "energy": "Utilities",
    "mobile": "Utilities",
    "waste service": "Utilities",
    "internet": "Utilities",
    "electric": "Utilities",
    "rent payment": "Housing",
    "upkeep": "Housing",
    "securenest": "Housing",
    "building manager": "Housing",
    "storagebox": "Housing",
    "gardencare": "Housing",
    "apartment service": "Housing",
    "postbox": "Housing",
    "new zealand": "Travel",
    "aotearoa": "Travel",
    "hostel": "Travel",
    "airport shuttle": "Travel",
    "milford": "Travel",
    "car rental": "Travel",
    "ferry terminal": "Travel",
    "queenstown": "Travel",
    "academy": "Education",
    "course": "Education",
    "language school": "Education",
    "learning": "Education",
    "workshop": "Education",
    "library": "Education",
    "studyhub": "Education",
    "classes": "Education",
    "pharmacy": "Health",
    "dental": "Health",
    "medical": "Health",
    "supplements": "Health",
    "optics": "Health",
    "appointment": "Health",
    "physiotherapy": "Health",
    "lab services": "Health",
    "cinema": "Entertainment",
    "music hall": "Entertainment",
    "gamecorner": "Entertainment",
    "museum": "Entertainment",
    "streaming box": "Entertainment",
    "theatre": "Entertainment",
    "puzzleroom": "Entertainment",
    "booktown": "Entertainment",
    "printworks": "Business",
    "clouddesk": "Business",
    "domainhouse": "Business",
    "officecart": "Business",
    "client deposit": "Business",
    "designmarket": "Business",
    "meetingroom": "Business",
    "postalpro": "Business",
    "fee": "Fees",
    "interest charge": "Fees",
    "payment received": "Payments",
    "card payment": "Payments",
    "refund": "Refunds",
    "return credit": "Refunds",
    "adjustment credit": "Refunds",
}


LlmCategorizer = Callable[[str, list[str]], str]
"""Function (description, candidates) -> category.
It must return one of `candidates`, or an empty string if undecidable.
"""


def categorize_one(
    description: str,
    existing_category: str = "",
    rules: dict[str, str] | None = None,
    llm: LlmCategorizer | None = None,
    candidates: Iterable[str] | None = None,
) -> str:
    """Determine a transaction category."""
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
    """Apply `categorize_one` row by row and write `df.category`."""
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
