#!/usr/bin/env python3
"""Gera negócios e clientes sintéticos (fictícios) para testar a skill. Nenhum dado real.

Usage: python3 make_sample.py examples/ [--seed 11] [--today 2026-11-12]
"""
import argparse
import csv
import os
import random
from datetime import date, timedelta

SEG = {"Saúde": 1.5, "Educação": 1.35, "Financeiro": 1.0, "Varejo": 0.75, "Indústria": 0.9, "Tecnologia": 0.8, "Serviços": 0.85}
SIZE = {"1-50": (0.6, 0.55), "51-200": (1.3, 1.0), "201-1000": (1.25, 1.6), "1000+": (0.7, 2.6)}
REG = {"Sudeste": 1.0, "Sul": 1.1, "Nordeste": 0.95, "Centro-Oeste": 0.9, "Norte": 0.8}
SRC = {"Indicação": 1.6, "Orgânico (SEO)": 1.2, "LinkedIn Ads": 0.9, "Google Ads": 0.7, "Outbound": 0.6, "Eventos": 0.9}
ERP = {"TOTVS": 1.25, "SAP": 0.9, "Senior": 1.2, "Planilha / nenhum": 0.6, "Outro": 1.0}
ROLE = {"Diretor(a) de RH": 1.3, "Gerente de T&D": 1.2, "CEO / Sócio": 0.9, "Analista": 0.55, "TI": 0.7}


def pick(rnd, d, w=None):
    return rnd.choices(list(d), weights=w or [1] * len(d))[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--today", default="2026-11-12")
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    today = date.fromisoformat(a.today)
    os.makedirs(a.out, exist_ok=True)
    deals, customers = [], []
    for i in range(1, 1101):
        seg, size, reg = pick(rnd, SEG, [14, 12, 14, 16, 14, 18, 12]), pick(rnd, SIZE, [34, 32, 22, 12]), pick(rnd, REG, [45, 20, 18, 10, 7])
        src, erp, role = pick(rnd, SRC, [12, 20, 15, 22, 18, 13]), pick(rnd, ERP, [25, 15, 15, 25, 20]), pick(rnd, ROLE, [20, 20, 25, 25, 10])
        p = 0.14 * SEG[seg] * SIZE[size][0] * REG[reg] * SRC[src] * ERP[erp] * ROLE[role]
        amount = round(rnd.lognormvariate(9.5, 0.45) * SIZE[size][1] * (1.15 if seg == "Saúde" else 1), -2)
        created = today - timedelta(days=rnd.randint(5, 760))
        cycle = int(rnd.gammavariate(3, 15) * (1.6 if size == "1000+" else 1) * (0.75 if src == "Indicação" else 1)) + 8
        age = (today - created).days
        company = f"Empresa {i:04d}"
        if cycle < age and rnd.random() < 0.88:
            won = rnd.random() < min(0.85, p)
            status = "Ganho" if won else "Perdido"
            closed = created + timedelta(days=cycle if won else int(cycle * rnd.uniform(0.6, 1.3)))
            closed = min(closed, today)
            if won:
                churn_p = {"1-50": 0.32, "51-200": 0.12, "201-1000": 0.08, "1000+": 0.15}[size] * (0.6 if seg in ("Saúde", "Educação") else 1.1)
                customers.append({"Empresa": company, "MRR": round(amount / 12 * rnd.uniform(0.9, 1.3), 2),
                                  "Status": "Cancelado" if rnd.random() < churn_p else "Ativo"})
        else:
            status, closed = "Aberto", created + timedelta(days=cycle + rnd.randint(0, 30))
        deals.append({"ID": i, "Negócio": f"{company} · {seg}", "Empresa": company, "Criado em": created.isoformat(),
                      "Fechado em": closed.isoformat(), "Status": status, "Etapa": status if status != "Aberto" else "Proposta",
                      "Valor (R$)": amount, "Origem": src, "Setor": seg, "Porte": size, "Região": reg,
                      "ERP do cliente": erp, "Cargo do decisor": role})
    for name, rows in (("negocios_icp_exemplo.csv", deals), ("clientes_exemplo.csv", customers)):
        with open(os.path.join(a.out, name), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    print(len(deals), len(customers))


if __name__ == "__main__":
    main()
