#!/usr/bin/env python3
"""Normaliza o export de negócios do CRM e mede a higiene dos dados.

Uso:
  python3 normalize.py negocios.csv --out funil_data [--map mapa.json] [--won-stages "Ganho"] [--lost-stages "Perdido"]
         [--pipeline "Vendas"] [--monthly-amount 12] [--monthdayfirst]

Saídas em --out: deals.json (negócios normalizados), columns.json (mapa usado), quality.json (higiene).
Saída 0 = ok; 2 = colunas obrigatórias ausentes (veja columns.json e passe --map).

Normalizes a CRM deals export (HubSpot, Pipedrive, RD Station, Salesforce, Ploomes, spreadsheets).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from carratu_data import (read_table, detect_columns, parse_date, parse_money, status_of, pctile, dump, strip)  # noqa

REQUIRED = ["created", "amount"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--out", default="funil_data")
    ap.add_argument("--map", help="JSON {campo: coluna} para corrigir a detecção")
    ap.add_argument("--won-stages", default="", help="etapas que significam ganho, separadas por vírgula")
    ap.add_argument("--lost-stages", default="", help="etapas que significam perda")
    ap.add_argument("--pipeline", default=None, help="filtra um pipeline pelo nome")
    ap.add_argument("--monthly-amount", type=float, default=None,
                    help="se o valor for MRR, multiplique por N (ex.: 12) para ter ACV")
    ap.add_argument("--monthdayfirst", action="store_true", help="datas no formato americano mm/dd")
    ap.add_argument("--today", default=None, help="data de referência AAAA-MM-DD (padrão: hoje)")
    ap.add_argument("--keep", default="", help="colunas extras a manter (atributos para ICP), separadas por vírgula")
    a = ap.parse_args()

    rows = read_table(a.file)
    if not rows:
        raise SystemExit("Arquivo vazio.")
    override = json.load(open(a.map, encoding="utf-8")) if a.map else None
    cols = detect_columns(list(rows[0].keys()), override=override)
    os.makedirs(a.out, exist_ok=True)
    dump({"detected": cols, "headers": list(rows[0].keys())}, os.path.join(a.out, "columns.json"))
    bad_keep = [c.strip() for c in a.keep.split(",") if c.strip() and c.strip() not in rows[0]]
    if bad_keep:
        raise SystemExit(f"--keep: colunas não encontradas: {bad_keep}")
    missing = [f for f in REQUIRED if f not in cols]
    if "status" not in cols and "stage" not in cols:
        missing.append("status|stage")
    if missing:
        print(json.dumps({"error": "colunas obrigatórias não encontradas", "missing": missing,
                          "headers": list(rows[0].keys()), "detected": cols}, ensure_ascii=False, indent=1))
        sys.exit(2)

    won_st = [x.strip() for x in a.won_stages.split(",") if x.strip()]
    lost_st = [x.strip() for x in a.lost_stages.split(",") if x.strip()]
    today = parse_date(a.today) if a.today else date.today()
    g = lambda r, f: r.get(cols[f], "") if f in cols else ""

    deals, dropped = [], Counter()
    for i, r in enumerate(rows):
        if a.pipeline and "pipeline" in cols and strip(g(r, "pipeline")) != strip(a.pipeline):
            dropped["outro pipeline"] += 1
            continue
        amt = parse_money(g(r, "amount"))
        if amt is not None and a.monthly_amount:
            amt *= a.monthly_amount
        d = {
            "id": str(g(r, "id") or i + 1),
            "name": str(g(r, "name") or ""),
            "created": parse_date(g(r, "created"), dayfirst=not a.monthdayfirst),
            "closed": parse_date(g(r, "closed"), dayfirst=not a.monthdayfirst),
            "stage": str(g(r, "stage") or "").strip(),
            "status": status_of(g(r, "status"), g(r, "stage"), won_st, lost_st),
            "amount": amt,
        }
        for f in ("owner", "source", "loss_reason", "segment", "company_size", "region", "company"):
            v = str(g(r, f) or "").strip()
            d[f] = v or None
        keep = [c.strip() for c in a.keep.split(",") if c.strip()]
        if keep:
            d["extra"] = {c: (str(r.get(c, "")).strip() or None) for c in keep}
        if d["created"] is None:
            dropped["sem data de criação"] += 1
            continue
        deals.append(d)

    # ---- higiene
    n = len(deals)
    closed = [d for d in deals if d["status"] != "open"]
    lost = [d for d in deals if d["status"] == "lost"]
    opn = [d for d in deals if d["status"] == "open"]
    ids = Counter(d["id"] for d in deals)
    amts = [d["amount"] for d in deals if d["amount"]]
    p99 = pctile(amts, 0.99) or 0
    checks = [
        ("amount_missing", "Negócios sem valor", "Deals without amount",
         sum(1 for d in deals if not d["amount"]), n, 0.05, 0.30, 25),
        ("closed_missing", "Fechados sem data de fechamento", "Closed deals without close date",
         sum(1 for d in closed if not d["closed"]), len(closed), 0.02, 0.20, 20),
        ("source_missing", "Negócios sem origem", "Deals without source",
         sum(1 for d in deals if not d["source"]), n, 0.10, 0.50, 15) if "source" in cols else None,
        ("loss_reason_missing", "Perdidos sem motivo de perda", "Lost deals without loss reason",
         sum(1 for d in lost if not d["loss_reason"]), len(lost), 0.10, 0.60, 15) if "loss_reason" in cols else None,
        ("owner_missing", "Negócios sem dono", "Deals without owner",
         sum(1 for d in deals if not d["owner"]), n, 0.02, 0.20, 10) if "owner" in cols else None,
        ("open_overdue", "Abertos com data de fechamento vencida", "Open deals with overdue close date",
         sum(1 for d in opn if d["closed"] and d["closed"] < today), len(opn), 0.10, 0.50, 10),
        ("negative_cycle", "Fechamento antes da criação", "Close date before create date",
         sum(1 for d in closed if d["closed"] and d["closed"] < d["created"]), len(closed), 0.0, 0.05, 3),
        ("duplicates", "IDs duplicados", "Duplicated IDs", sum(c - 1 for c in ids.values() if c > 1), n, 0.0, 0.05, 2),
    ]
    checks = [c for c in checks if c]
    not_tracked = [f for f in ("source", "loss_reason", "owner") if f not in cols]
    out, score_num, score_den = [], 0.0, 0.0
    for key, pt, en, bad, den, good_t, bad_t, w in checks:
        rate = bad / den if den else 0.0
        s = 100.0 if rate <= good_t else 0.0 if rate >= bad_t else 100 * (bad_t - rate) / (bad_t - good_t)
        status = "pass" if s >= 75 else "warn" if s >= 40 else "fail"
        out.append({"key": key, "label_pt": pt, "label_en": en, "count": bad, "base": den, "rate": rate,
                    "score": round(s), "status": status, "weight": w})
        score_num += s * w
        score_den += w
    # campo não rastreado conta como falha: dado que não existe não pode ser analisado
    for f in not_tracked:
        w = {"source": 15, "loss_reason": 15, "owner": 10}[f]
        out.append({"key": f + "_not_tracked", "label_pt": f"Campo '{f}' não existe no export",
                    "label_en": f"Field '{f}' not in export", "count": None, "base": n, "rate": 1.0, "score": 0,
                    "status": "fail", "weight": w})
        score_den += w
    q = {"score": round(score_num / score_den) if score_den else None, "checks": out,
         "outliers_amount": [d["id"] for d in deals if d["amount"] and p99 and d["amount"] > 5 * p99],
         "rows_in": len(rows), "rows_used": n, "dropped": dict(dropped),
         "status_counts": dict(Counter(d["status"] for d in deals)),
         "stages_seen": Counter(d["stage"] for d in deals).most_common(),
         "date_range": [min(d["created"] for d in deals), max(d["created"] for d in deals)] if deals else None,
         "today": today}
    dump(deals, os.path.join(a.out, "deals.json"))
    dump(q, os.path.join(a.out, "quality.json"))
    print(json.dumps({"rows_used": n, "status": q["status_counts"], "quality_score": q["score"],
                      "columns": cols, "stages_seen": q["stages_seen"][:20], "dropped": q["dropped"]},
                     ensure_ascii=False, indent=1, default=str))
    if q["status_counts"].get("won", 0) == 0:
        print("AVISO: nenhum negócio ganho detectado. Confira --won-stages ou a coluna de status.", file=sys.stderr)


if __name__ == "__main__":
    main()
