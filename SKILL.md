---
name: carratu-icp-reverso
description: ICP reverso, por Ubirajara Carratu: descobre o perfil de cliente ideal real a partir dos negócios ganhos e perdidos do CRM (e da retenção, se houver), com índice estatístico, tiers A/B/C, modelo de pontuação para o CRM e pipeline atual classificado. Use quando o usuário pedir para definir ou validar o ICP, perfil de cliente ideal, "quem é meu melhor cliente", segmentação de contas, lead scoring baseado em dados, quais segmentos ou portes priorizar, ou por que o time persegue clientes que não fecham. Também em inglês (ideal customer profile from data, ICP analysis, account scoring). Entrega relatório DOCX e PDF e CSVs prontos para o CRM.
---

# ICP reverso (Metodologia Carratu)

Autor: Ubirajara Carratu · Carratu revenue growth consulting. Versão 1.0.0 (nov/2026).
Licença: PolyForm Noncommercial 1.0.0 (ver `NOTICE.md`).

Você vai descobrir o ICP pelo que os dados mostram, não pelo que o time acha, e transformar isso em decisão: onde focar,
o que desqualificar e como pontuar contas no CRM.

**Idioma:** o do usuário (`--lang pt|en`, `"lang"` no `report.json`). `SKILL_DIR` é a pasta deste arquivo; trabalhe
numa pasta gravável com `icp_data/` e `outputs/`.

Referências: `references/method.md` (índice, encolhimento, significância, modelo), `references/data-export.md`
(como tirar os dados de cada CRM), `references/report-schema.md`.

---

## Etapa 0: Escuta ativa (uma rodada de perguntas)

1. **ICP declarado**: "Como vocês descrevem o cliente ideal hoje?" Esta resposta é a hipótese que os dados vão testar.
   Guarde-a para a seção "declarado vs real".
2. **Dados**: conector de CRM ou export. Quais atributos existem além de segmento e porte (ERP ou stack, cargo do
   decisor, nº de unidades, modelo de negócio)? Peça os que o comercial usa para qualificar.
3. **Retenção**: existe base de clientes com status ativo/cancelado e receita atual? (opcional, recomendado)
4. **Formato**: relatório completo, 1 página ou os dois; e se quer o modelo de pontuação para o CRM.

Exija amostra: com menos de ~150 negócios fechados ou ~30 ganhos, avise que o resultado será indicativo e sugira ampliar
a janela.

## Etapa 1: Dados

```bash
python3 SKILL_DIR/scripts/normalize.py negocios.csv --out icp_data --keep "ERP do cliente,Cargo do decisor" [--map mapa.json]
```
`--keep` mantém as colunas extras (nomes exatos do arquivo). Confira contagens e cobertura dos campos no resumo.

## Etapa 2: Cálculo

```bash
python3 SKILL_DIR/scripts/icp.py icp_data --attrs "segment,company_size,region,source,extra:ERP do cliente,extra:Cargo do decisor" \
   [--customers clientes.csv] [--period-days 730] [--min-n 8] --lang pt
```
Gera `metrics.json`, `auto_sections.json`, `charts/`, `icp_scoring.csv` (modelo para o CRM) e `open_scored.csv`
(pipeline aberto pontuado, do maior para o menor).

## Etapa 3: Leitura de analista

Com números do resumo, responda: qual é o ICP real (2 ou 3 perfis A com (sig.) ou coerentes entre atributos)? Em que
ele difere do declarado? Quanto do pipeline atual está em C? De que canais vêm os perfis A? Algum perfil fecha bem e
cancela muito? Quais perfis C viram critério de desqualificação?

Escreva o ICP final como uma ficha curta (seção própria no `report.json`): **quem** (segmento, porte, contexto
tecnológico), **quem decide**, **gatilho de compra**, **por onde chega**, **quem não é ICP**. Gatilhos de compra vêm
de conversas e do usuário, não do script: diga isso.

## Etapa 4: Relatório

Escreva `icp_data/report.json` (`report-schema.md`). Para `score`, use a parcela do valor do pipeline aberto em Tier A
ou B como "aderência do pipeline ao ICP" (0-100) e explique isso em `methodology`. Gere:
```bash
python3 SKILL_DIR/scripts/carratu_report.py icp_data/report.json --auto icp_data/auto_sections.json --out outputs --format full
```
Confira a primeira página como imagem e entregue o relatório **e** `icp_scoring.csv` e `open_scored.csv`.

## Etapa 5: Resumo no chat

```
**[Empresa]: ICP reverso** · [n] negócios fechados · [período]
ICP real: (1 frase) · Declarado vs real: (1 frase)
Pipeline: XX% do valor em perfil A/B, XX% em C
**3 decisões:** (foco, desqualificação, canal)
```
Ofereça: levar o modelo de pontuação para o CRM conectado, gerar a lista de contas-alvo com `carratu-abm-plays` ou
rever o diagnóstico de funil por tier.

---

## Princípios inegociáveis

- **Amostra decide o tom.** Sem (sig.) e com poucos negócios, é hipótese a testar, não ICP.
- **Receita, não volume.** Win rate alto com ticket baixo e churn alto não é perfil A.
- **Correlação não é causa.** Atributos andam juntos; aponte quando dois perfis "ótimos" forem o mesmo cliente.
- **Dados de pessoas**: use cargo, nunca nome de contato, no relatório.
- **Específico.** "Indústria de 201 a 1000 funcionários com SAP, decisão no RH" e não "empresas médias".
