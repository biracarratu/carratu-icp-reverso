#!/usr/bin/env python3
"""ICP reverso: descobre o perfil de cliente que de fato compra, paga mais e fecha mais rápido.

Uso:
  python3 icp.py icp_data [--attrs segment,company_size,region,source,extra:Tecnologia] [--period-days 730]
         [--customers clientes.csv] [--min-n 8] [--lang pt|en] [--today AAAA-MM-DD]

Entrada: icp_data/deals.json (gerado por normalize.py). Opcional: CSV de clientes com empresa, receita atual e status
(ativo/cancelado) para medir retenção por perfil.
Saídas: metrics.json, auto_sections.json, charts/, icp_scoring.csv (pontos por atributo, para levar ao CRM) e
open_scored.csv (pipeline aberto pontuado pelo modelo).

Reverse ICP: finds the customer profile that actually buys, pays more and closes faster.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import os
import sys
from collections import defaultdict
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from carratu_data import (read_table, detect_columns, parse_date, parse_money, mean, median, wilson, strip,  # noqa
                          fmt_money, fmt_pct, fmt_num, fmt_days, dump)
import carratu_charts as C  # noqa

T = {
    "pt": {"segment": "Segmento", "company_size": "Porte", "region": "Região", "source": "Origem", "owner": "Vendedor",
           "kpis": "Base analisada", "closed": "Fechados", "won": "Ganhos", "wr": "Win rate", "ticket": "Ticket médio",
           "cycle": "Ciclo mediano", "index": "Índice ICP", "value": "Valor", "share_rev": "% da receita", "lift": "Lift",
           "attr": "Atributo", "by": "Perfil por", "combos": "Combinações que definem o ICP real", "combo": "Perfil",
           "tier": "Tier", "tiers": "Tiers de ICP", "pipeline": "Pipeline aberto por tier", "deals": "Negócios",
           "pipe_value": "Valor aberto", "share": "% do pipeline", "model": "Modelo de pontuação (para o CRM)",
           "points": "Pontos", "churn": "Churn", "rev_now": "Receita atual média", "small": "amostra pequena",
           "note_index": "Índice ICP = (win rate ÷ média) × (ticket ÷ média) × √(ciclo médio ÷ ciclo), ajustado para amostras pequenas (encolhido em direção a 1). Acima de 1,3 = perfil A; 0,8 a 1,3 = B; abaixo de 0,8 = C. (sig.) = win rate estatisticamente diferente da média (IC 95% não inclui a média). Combinações exigem 16 fechados e 3 ganhos.",
           "chart_title": "Win rate × ticket por segmento (tamanho do ponto = negócios fechados)",
           "overall": "Média da base", "retention": "Retenção por perfil (clientes atuais)", "customers": "Clientes",
           "model_note": "Some os pontos dos atributos de cada conta. 100 = perfil médio; acima de 130 = Tier A; abaixo de 80 = Tier C. Atributo vazio vale 0 pontos de ajuste.",
           "fit": "Fit"},
    "en": {"segment": "Segment", "company_size": "Company size", "region": "Region", "source": "Source", "owner": "Rep",
           "kpis": "Data analyzed", "closed": "Closed", "won": "Won", "wr": "Win rate", "ticket": "Avg. deal size",
           "cycle": "Median cycle", "index": "ICP index", "value": "Value", "share_rev": "% of revenue", "lift": "Lift",
           "attr": "Attribute", "by": "Profile by", "combos": "Combinations that define the real ICP", "combo": "Profile",
           "tier": "Tier", "tiers": "ICP tiers", "pipeline": "Open pipeline by tier", "deals": "Deals",
           "pipe_value": "Open value", "share": "% of pipeline", "model": "Scoring model (for your CRM)",
           "points": "Points", "churn": "Churn", "rev_now": "Avg. current revenue", "small": "small sample",
           "note_index": "ICP index = (win rate ÷ average) × (deal size ÷ average) × √(average cycle ÷ cycle), shrunk toward 1 for small samples. Above 1.3 = tier A; 0.8 to 1.3 = B; below 0.8 = C. (sig.) = win rate statistically different from baseline (95% CI excludes it). Combinations require 16 closed and 3 won deals.",
           "chart_title": "Win rate × deal size by segment (dot size = closed deals)",
           "overall": "Baseline", "retention": "Retention by profile (current customers)", "customers": "Customers",
           "model_note": "Add up attribute points for each account. 100 = average profile; above 130 = Tier A; below 80 = Tier C. Empty attribute adds 0.",
           "fit": "Fit"},
}
K_SHRINK = 12  # quanto maior, mais conservador com amostras pequenas


def val(d, attr):
    if attr.startswith("extra:"):
        return (d.get("extra") or {}).get(attr[6:])
    return d.get(attr)


def stats(ds, base, k=K_SHRINK):
    won = [d for d in ds if d["status"] == "won"]
    n = len(ds)
    wr = len(won) / n if n else None
    tk = mean([d["amount"] for d in won if d["amount"]])
    cy = median([(d["closed"] - d["created"]).days for d in won if d["closed"] and d["closed"] >= d["created"]])
    raw = None
    if wr is not None and tk and base["wr"] and base["tk"]:
        raw = (wr / base["wr"]) * (tk / base["tk"]) * math.sqrt((base["cy"] or 1) / (cy or base["cy"] or 1))
    elif wr is not None and base["wr"]:
        raw = wr / base["wr"]
    w = n / (n + k)
    idx = 1 + w * ((raw if raw is not None else 0.0) - 1) if raw is not None else 1 - w  # sem ganhos → puxa para baixo
    lo, hi = wilson(len(won), n)
    sig = lo is not None and base["wr"] is not None and (lo > base["wr"] or hi < base["wr"])
    return {"closed": n, "won": len(won), "win_rate": wr, "ci": [lo, hi], "ticket": tk, "cycle": cy, "significant": sig,
            "won_value": sum(d["amount"] or 0 for d in won), "raw_index": raw, "index": idx}


def tier(i):
    return "A" if i >= 1.3 else "B" if i >= 0.8 else "C"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir")
    ap.add_argument("--attrs", default="segment,company_size,region,source")
    ap.add_argument("--period-days", type=int, default=730)
    ap.add_argument("--customers", default=None)
    ap.add_argument("--min-n", type=int, default=8)
    ap.add_argument("--lang", default="pt")
    ap.add_argument("--currency", default=None)
    ap.add_argument("--today", default=None)
    a = ap.parse_args()
    lang = a.lang if a.lang in T else "pt"
    t = T[lang]
    M = lambda v: fmt_money(v, lang, a.currency)
    P = lambda v: fmt_pct(v, lang)
    F = lambda v: "-" if v is None else (f"{v:.2f}".replace(".", ",") if lang == "pt" else f"{v:.2f}")
    deals = json.load(open(os.path.join(a.data_dir, "deals.json"), encoding="utf-8"))
    q = json.load(open(os.path.join(a.data_dir, "quality.json"), encoding="utf-8"))
    for d in deals:
        d["created"] = parse_date(d["created"])
        d["closed"] = parse_date(d["closed"]) if d.get("closed") else None
    today = parse_date(a.today) if a.today else (parse_date(q.get("today")) or date.today())
    start = today - timedelta(days=a.period_days)
    closed = [d for d in deals if d["status"] != "open" and d["closed"] and start <= d["closed"] <= today]
    opn = [d for d in deals if d["status"] == "open"]
    won = [d for d in closed if d["status"] == "won"]
    base = {"wr": len(won) / len(closed) if closed else None, "tk": mean([d["amount"] for d in won if d["amount"]]),
            "cy": median([(d["closed"] - d["created"]).days for d in won if d["closed"] and d["closed"] >= d["created"]])}
    total_won = sum(d["amount"] or 0 for d in won)
    attrs = [x.strip() for x in a.attrs.split(",") if x.strip()]
    attrs = [x for x in attrs if any(val(d, x) for d in closed)]
    label = lambda x: t.get(x, x[6:] if x.startswith("extra:") else x)
    ch = os.path.join(a.data_dir, "charts")
    os.makedirs(ch, exist_ok=True)

    # ---- por atributo
    by = {}
    for at in attrs:
        g = defaultdict(list)
        for d in closed:
            v = val(d, at)
            if v:
                g[v].append(d)
        rows = []
        for v, ds in g.items():
            s = stats(ds, base)
            s["value"] = v
            s["share_rev"] = s["won_value"] / total_won if total_won else None
            rows.append(s)
        rows.sort(key=lambda s: -s["index"])
        by[at] = rows

    # ---- combinações de 2 atributos
    combos = []
    for a1, a2 in itertools.combinations(attrs, 2):
        g = defaultdict(list)
        for d in closed:
            v1, v2 = val(d, a1), val(d, a2)
            if v1 and v2:
                g[(v1, v2)].append(d)
        for (v1, v2), ds in g.items():
            # combinações: amostra mínima maior e encolhimento mais forte (muitas comparações = mais ruído)
            if len(ds) >= max(2 * a.min_n, 16) and sum(1 for d in ds if d["status"] == "won") >= 3:
                s = stats(ds, base, k=2 * K_SHRINK)
                s["profile"] = f"{label(a1)}: {v1} · {label(a2)}: {v2}"
                s["share_rev"] = s["won_value"] / total_won if total_won else None
                combos.append(s)
    combos.sort(key=lambda s: -s["index"])

    # ---- modelo de pontos (aditivo, log do índice encolhido) e pontuação do pipeline aberto
    model = []
    pts = {}
    for at in attrs:
        for s in by[at]:
            p = round(100 * math.log(max(s["index"], 0.05)) / max(1, len(attrs)) * 1.5)
            pts[(at, s["value"])] = p
            model.append({"attribute": label(at), "value": s["value"], "points": p, "closed": s["closed"], "index": s["index"]})
    with open(os.path.join(a.data_dir, "icp_scoring.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["atributo" if lang == "pt" else "attribute", "valor" if lang == "pt" else "value",
                    "pontos" if lang == "pt" else "points", "fechados" if lang == "pt" else "closed", "indice" if lang == "pt" else "index"])
        for m in model:
            w.writerow([m["attribute"], m["value"], m["points"], m["closed"], f"{m['index']:.2f}"])

    def score(d):
        return 100 + sum(pts.get((at, val(d, at)), 0) for at in attrs)

    def tier_s(sc):
        return "A" if sc >= 130 else "B" if sc >= 80 else "C"

    # validação do modelo nos fechados (dentro da amostra: indicativo, não prova)
    val_t = defaultdict(lambda: [0, 0, 0.0])
    for d in closed:
        tt = tier_s(score(d))
        val_t[tt][0] += 1
        val_t[tt][1] += d["status"] == "won"
        val_t[tt][2] += (d["amount"] or 0) if d["status"] == "won" else 0
    pipe = defaultdict(lambda: [0, 0.0])
    with open(os.path.join(a.data_dir, "open_scored.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "negocio" if lang == "pt" else "deal", "valor" if lang == "pt" else "value", "pontos" if lang == "pt" else "score", "tier"])
        for d in sorted(opn, key=lambda d: -score(d)):
            sc = score(d)
            tt = tier_s(sc)
            pipe[tt][0] += 1
            pipe[tt][1] += d["amount"] or 0
            w.writerow([d["id"], d.get("name") or "", d["amount"] or "", sc, tt])
    pipe_total = sum(v[1] for v in pipe.values()) or 1

    # ---- retenção (opcional)
    retention = None
    if a.customers:
        rows = read_table(a.customers)
        cols = detect_columns(list(rows[0].keys()), {
            "company": ["empresa", "company", "cliente", "conta", "account name", "nome"],
            "revenue": ["mrr", "receita", "valor", "arr", "revenue", "mensalidade"],
            "status": ["status", "situacao", "ativo", "churn", "cancelado", "estado"]})
        comp_attr = {}
        for d in won:
            if d.get("company"):
                comp_attr[strip(d["company"])] = d
        g = defaultdict(lambda: [0, 0, []])
        for r in rows:
            d = comp_attr.get(strip(r.get(cols.get("company"), "")))
            if not d:
                continue
            churned = any(k in strip(r.get(cols.get("status"), "")) for k in ("cancel", "churn", "inativ", "perdid", "lost"))
            rev = parse_money(r.get(cols.get("revenue"), ""))
            for at in attrs:
                v = val(d, at)
                if v:
                    g[(at, v)][0] += 1
                    g[(at, v)][1] += churned
                    if rev and not churned:
                        g[(at, v)][2].append(rev)
        retention = [{"attribute": label(at), "value": v, "customers": n, "churn": c / n if n else None,
                      "rev_mean": mean(revs)} for (at, v), (n, c, revs) in g.items() if n >= 3]
        retention.sort(key=lambda r: (r["attribute"], r["churn"] if r["churn"] is not None else 1))

    metrics = {"period": {"start": start, "end": today}, "base": base, "closed": len(closed), "won": len(won),
               "won_value": total_won, "open": len(opn), "attributes": attrs, "by_attribute": by, "combos": combos[:30],
               "model": model, "model_validation": {k: {"closed": v[0], "win_rate": v[1] / v[0] if v[0] else None,
                                                         "won_value": v[2]} for k, v in val_t.items()},
               "pipeline_by_tier": {k: {"deals": v[0], "value": v[1], "share": v[1] / pipe_total} for k, v in pipe.items()},
               "retention": retention}
    dump(metrics, os.path.join(a.data_dir, "metrics.json"))

    # ---- blocos
    S = [{"title": t["kpis"], "blocks": [{"type": "kpis", "items": [
        {"label": t["closed"], "value": fmt_num(len(closed), lang)}, {"label": t["won"], "value": fmt_num(len(won), lang)},
        {"label": t["wr"] + " · " + t["overall"].lower(), "value": P(base["wr"])}, {"label": t["ticket"], "value": M(base["tk"])},
        {"label": t["cycle"], "value": fmt_days(base["cy"], lang)},
        {"label": t["pipeline"] + " A", "value": P(pipe["A"][1] / pipe_total), "status": "pass" if pipe["A"][1] / pipe_total >= 0.4 else "warn"},
        {"label": t["pipeline"] + " C", "value": P(pipe["C"][1] / pipe_total), "status": "fail" if pipe["C"][1] / pipe_total >= 0.3 else "warn"},
        {"label": "Atributos" if lang == "pt" else "Attributes", "value": str(len(attrs))}]}]}]
    if combos:
        S.append({"title": t["combos"], "page_break_before": True, "blocks": [{"type": "table",
                  "header": [t["combo"], t["closed"], t["wr"], t["ticket"], t["cycle"], t["share_rev"], t["index"], t["tier"]],
                  "rows": [[c["profile"] + (" (sig.)" if c["significant"] else ""), str(c["closed"]), P(c["win_rate"]), M(c["ticket"]), fmt_days(c["cycle"], lang),
                            P(c["share_rev"]), F(c["index"]), tier(c["index"]) + "|" + {"A": "pass", "B": "warn", "C": "fail"}[tier(c["index"])]]
                           for c in combos[:12]],
                  "widths": [5.6, 1.6, 1.7, 2.1, 1.8, 1.6, 1.4, 1.2], "status_col": 7, "size": 8.5},
                  {"type": "text", "text": t["note_index"]}]})
    for at in attrs:
        rows = by[at]
        blocks = []
        if at == attrs[0] and len(rows) >= 3:
            fn = "charts/icp_scatter.png"
            C.scatter([(r["ticket"] or 0, (r["win_rate"] or 0) * 100, r["value"][:18]) for r in rows if r["closed"] >= a.min_n],
                      os.path.join(a.data_dir, fn), title=t["chart_title"], xlabel=t["ticket"], ylabel=t["wr"] + " (%)",
                      quad=(base["tk"] or 0, (base["wr"] or 0) * 100))
            blocks.append({"type": "chart", "path": fn, "width_cm": 14})
        blocks.append({"type": "table", "header": [label(at), t["closed"], t["wr"], t["ticket"], t["cycle"], t["share_rev"],
                                                    t["index"], t["tier"]],
                       "rows": [[r["value"] + ("" if r["closed"] >= a.min_n else f" ({t['small']})") + (" (sig.)" if r["significant"] else ""), str(r["closed"]),
                                 P(r["win_rate"]), M(r["ticket"]), fmt_days(r["cycle"], lang), P(r["share_rev"]), F(r["index"]),
                                 tier(r["index"]) + "|" + {"A": "pass", "B": "warn", "C": "fail"}[tier(r["index"])]] for r in rows[:12]],
                       "widths": [4.6, 1.6, 1.7, 2.2, 2.0, 1.8, 1.6, 1.5], "status_col": 7, "size": 8.5})
        S.append({"title": f"{t['by']} {label(at).lower()}", "blocks": blocks})
    S.append({"title": t["pipeline"], "blocks": [{"type": "table", "header": [t["tier"], t["deals"], t["pipe_value"], t["share"],
              ("Win rate histórico do tier" if lang == "pt" else "Historical tier win rate")],
              "rows": [[k, str(pipe[k][0]), M(pipe[k][1]), P(pipe[k][1] / pipe_total),
                        P(val_t[k][1] / val_t[k][0]) if val_t[k][0] else "-"] for k in ("A", "B", "C")],
              "widths": [2, 3, 4, 3.5, 4.5]}]})
    if retention:
        S.append({"title": t["retention"], "blocks": [{"type": "table", "header": [t["attr"], t["value"], t["customers"], t["churn"], t["rev_now"]],
                  "rows": [[r["attribute"], r["value"], str(r["customers"]), P(r["churn"]), M(r["rev_mean"])] for r in retention[:20]],
                  "widths": [3.5, 5, 2.5, 2.5, 3.5]}]})
    S.append({"title": t["model"], "position": "end", "blocks": [{"type": "table", "header": [t["attr"], t["value"], t["points"], t["closed"]],
              "rows": [[m["attribute"], m["value"], f"{m['points']:+d}", str(m["closed"])] for m in model], "widths": [4, 7, 3, 3], "size": 8.5},
              {"type": "text", "text": t["model_note"]}]})
    dump({"sections": S}, os.path.join(a.data_dir, "auto_sections.json"))

    print(json.dumps({"base": base, "closed": len(closed), "won": len(won),
                      "top_combos": [(c["profile"], c["closed"], round(c["win_rate"], 3), round(c["ticket"] or 0), c["cycle"],
                                      round(c["index"], 2), round(c["share_rev"] or 0, 3), c["significant"]) for c in combos[:8]],
                      "worst_combos": [(c["profile"], c["closed"], round(c["win_rate"], 3), round(c["index"], 2)) for c in combos[-5:]],
                      "by_attribute": {at: [(r["value"], r["closed"], round(r["win_rate"] or 0, 3), round(r["ticket"] or 0),
                                             r["cycle"], round(r["index"], 2), r["significant"]) for r in by[at]] for at in attrs},
                      "pipeline_by_tier": metrics["pipeline_by_tier"], "model_validation": metrics["model_validation"],
                      "retention": retention[:10] if retention else None}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
