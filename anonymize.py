"""anonymize.py — find/replace consistant pour un export CSV de carte de credit.

Usage:
    python anonymize.py --src in.csv --dst out.csv --mapping merchant_mapping.yaml
    python anonymize.py --src in.csv --mapping merchant_mapping.yaml --dry-run
    python anonymize.py --src in.csv --mapping merchant_mapping.yaml --check

Garanties:
    - 1 source -> 1 cible : si "Tim Hortons" apparait 106 fois en entree,
      le mapping est applique 106 fois et "Coffee Gossip" apparait 106 fois.
    - Tout marchand absent du mapping fait l'objet d'un avertissement (sauf
      les exceptions whitelistees ci-dessous).
    - Encodage UTF-8 strict en lecture et ecriture (les accents francais
      passent a travers correctement).
    - Idempotent : relancer le script sur la sortie ne change rien si la
      sortie ne contient deja que des noms cibles.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

import yaml


# Marchands "systeme" qui n'ont pas besoin d'etre anonymises (etiquettes
# generiques). Ils sont autorises a passer sans etre dans le mapping.
ALLOWED_PASSTHROUGH = {
    "Programme remise en argent",
    "Avance de fonds",
}


def load_mapping(path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """Retourne (merchants, categories, headers) depuis le YAML."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return (
        dict(data.get("merchants") or {}),
        dict(data.get("categories") or {}),
        dict(data.get("headers") or {}),
    )


def read_csv(src: Path) -> tuple[list[str], list[list[str]]]:
    """Lit le CSV (separateur ;, quote "), retourne (header, rows)."""
    with src.open(encoding="utf-8", newline="") as fin:
        reader = csv.reader(fin, delimiter=";", quotechar='"')
        rows = list(reader)
    if not rows:
        raise ValueError(f"{src} est vide.")
    header, *body = rows
    return header, body


def apply_mapping(
    header: list[str],
    body: list[list[str]],
    merchants: dict[str, str],
    categories: dict[str, str],
    headers_map: dict[str, str],
) -> tuple[list[str], list[list[str]], Counter, Counter, set[str], set[str]]:
    """Applique le mapping. Retourne :
        new_header, new_body, merchant_counts, category_counts,
        unmapped_merchants, unmapped_categories
    """
    new_header = [headers_map.get(h, h) for h in header]
    desc_idx = header.index("Description") if "Description" in header else 2
    cat_idx = header.index("Categorie") if "Categorie" in header else 3

    merchant_counts: Counter = Counter()
    category_counts: Counter = Counter()
    unmapped_merchants: set[str] = set()
    unmapped_categories: set[str] = set()

    new_body: list[list[str]] = []
    for row in body:
        if len(row) <= max(desc_idx, cat_idx):
            new_body.append(row)
            continue
        old_desc = row[desc_idx]
        old_cat = row[cat_idx]
        new_desc = merchants.get(old_desc, old_desc)
        new_cat = categories.get(old_cat, old_cat)
        if new_desc != old_desc:
            merchant_counts[(old_desc, new_desc)] += 1
        elif old_desc not in ALLOWED_PASSTHROUGH:
            unmapped_merchants.add(old_desc)
        if new_cat != old_cat:
            category_counts[(old_cat, new_cat)] += 1
        elif old_cat and old_cat not in categories.values():
            # categorie inchangee : on enregistre seulement si elle n'a pas
            # deja sa forme corrigee (sinon ce serait un faux positif sur un
            # second passage idempotent)
            unmapped_categories.add(old_cat)
        new_row = list(row)
        new_row[desc_idx] = new_desc
        new_row[cat_idx] = new_cat
        new_body.append(new_row)

    return new_header, new_body, merchant_counts, category_counts, unmapped_merchants, unmapped_categories


def write_csv(dst: Path, header: list[str], body: list[list[str]]) -> None:
    """Ecrit le CSV avec le meme dialecte que la source (separateur ;,
    quotation des champs non numeriques pour que les accents soient
    proteges)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(
            fout,
            delimiter=";",
            quotechar='"',
            quoting=csv.QUOTE_NONNUMERIC,
        )
        writer.writerow(header)
        writer.writerows(body)


def print_report(
    merchant_counts: Counter,
    category_counts: Counter,
    unmapped_merchants: set[str],
    unmapped_categories: set[str],
    total_rows: int,
) -> None:
    """Affiche un rapport detaille des transformations effectuees."""
    print("=" * 70)
    print(f"RAPPORT D'ANONYMISATION  ({total_rows} lignes traitees)")
    print("=" * 70)

    print()
    print(f"--- Marchands renommes ({sum(merchant_counts.values())} occurrences, "
          f"{len(merchant_counts)} mappings distincts) ---")
    for (old, new), n in merchant_counts.most_common():
        print(f"  {n:4d}  {old!r:50s}  ->  {new!r}")

    print()
    print(f"--- Categories renommees ({sum(category_counts.values())} occurrences, "
          f"{len(category_counts)} mappings distincts) ---")
    for (old, new), n in category_counts.most_common():
        print(f"  {n:4d}  {old!r:35s}  ->  {new!r}")

    if unmapped_merchants:
        print()
        print(f"!!! AVERTISSEMENT : {len(unmapped_merchants)} marchands non mappes "
              "(passes a l'identique) :")
        for m in sorted(unmapped_merchants):
            print(f"  - {m!r}")

    if unmapped_categories:
        print()
        print(f"NOTE : {len(unmapped_categories)} categories laissees telles quelles "
              "(deja correctes ou non listees dans le YAML) :")
        for c in sorted(unmapped_categories):
            print(f"  - {c!r}")

    print()


def check_no_real_names(
    body: list[list[str]],
    merchants: dict[str, str],
    desc_idx: int = 2,
) -> list[str]:
    """Apres anonymisation : verifie qu'aucune cle (nom reel) ne reste
    dans la colonne Description."""
    real_names = set(merchants.keys())
    seen: list[str] = []
    for row in body:
        if len(row) > desc_idx and row[desc_idx] in real_names:
            seen.append(row[desc_idx])
    return seen


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--src", type=Path, required=True, help="CSV source")
    parser.add_argument("--dst", type=Path, help="CSV destination (omis avec --dry-run)")
    parser.add_argument("--mapping", type=Path, required=True, help="merchant_mapping.yaml")
    parser.add_argument("--dry-run", action="store_true", help="afficher le rapport sans rien ecrire")
    parser.add_argument("--check", action="store_true",
                        help="verifie que la sortie ne contient plus de nom reel")
    args = parser.parse_args(argv)

    if not args.dry_run and args.dst is None:
        parser.error("--dst est requis sauf en mode --dry-run")

    merchants, categories, headers_map = load_mapping(args.mapping)
    print(f"Mapping charge : {len(merchants)} marchands, "
          f"{len(categories)} categories, {len(headers_map)} headers.")

    header, body = read_csv(args.src)
    print(f"Source lue : {args.src} ({len(body)} lignes, header={header})")

    new_header, new_body, mcnt, ccnt, um, uc = apply_mapping(
        header, body, merchants, categories, headers_map
    )
    print_report(mcnt, ccnt, um, uc, len(body))

    if args.dry_run:
        print("(dry-run : rien ecrit)")
        return 0 if not um else 2

    write_csv(args.dst, new_header, new_body)
    print(f"Sortie ecrite : {args.dst} ({len(new_body)} lignes, header={new_header})")

    if args.check:
        leaks = check_no_real_names(new_body, merchants)
        if leaks:
            print(f"!!! ECHEC : {len(leaks)} nom(s) reel(s) restant dans la sortie :")
            for n in Counter(leaks).most_common():
                print(f"  {n[1]:4d}  {n[0]!r}")
            return 3
        print("OK : aucun nom reel ne subsiste dans la sortie.")

    return 0 if not um else 2


if __name__ == "__main__":
    raise SystemExit(main())
