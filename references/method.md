# Método: ICP reverso (Metodologia Carratu)

O ICP declarado nasce de opinião ("atendemos médias empresas de tecnologia"). O ICP reverso nasce dos negócios fechados:
**quem compra mais, paga mais, fecha mais rápido e fica mais tempo**. English: same method; keys match `metrics.json`.

## Base

- Negócios **fechados** (ganhos e perdidos) na janela (`--period-days`, padrão 730 dias: ICP precisa de amostra).
- Atributos firmográficos e de contexto: segmento, porte, região, origem e quaisquer colunas extras (`--keep` no
  normalize e `extra:Nome da coluna` no `--attrs`): ERP ou stack usada, cargo do decisor, modelo de negócio, número de
  unidades, maturidade. **Os atributos extras costumam ser os mais reveladores.**
- Opcional: base de clientes com status (ativo/cancelado) e receita atual, para medir retenção por perfil. Um perfil que
  fecha fácil e cancela rápido não é ICP.

## Índice ICP

```
bruto  = (win rate do perfil ÷ win rate da base) × (ticket do perfil ÷ ticket da base) × √(ciclo da base ÷ ciclo do perfil)
índice = 1 + (n ÷ (n + k)) × (bruto − 1)        k = 12 para valores únicos, 24 para combinações
```
- Junta as três alavancas de receita (conversão, tamanho, velocidade). O ciclo entra com raiz para não dominar.
- O **encolhimento** puxa perfis de amostra pequena para a média: 10 negócios com 50% de win rate não viram ICP.
- **(sig.)**: o IC 95% do win rate do perfil não inclui o win rate da base. Sem (sig.), trate como hipótese.
- Tiers: **A** ≥ 1,3 · **B** 0,8 a 1,3 · **C** < 0,8.
- Combinações de dois atributos exigem 16 fechados e 3 ganhos. Com muitos atributos, há muitas combinações: algumas
  vão parecer ótimas por acaso. Priorize as que aparecem coerentes com os atributos isolados.

## Modelo de pontuação

Pontos aditivos por valor de atributo: `100 × ln(índice) ÷ nº de atributos × 1,5`. Conta = 100 + soma dos pontos.
≥ 130 = Tier A; < 80 = Tier C. Exportado em `icp_scoring.csv` para virar propriedade de pontuação no CRM (HubSpot:
pontuação de lead/empresa; RD e Pipedrive: campo calculado ou automação).

A validação impressa (win rate por tier nos negócios fechados) é **dentro da amostra**: mostra que o modelo separa,
não prova que prevê. Prova é aplicar ao pipeline novo e medir em 90 dias.

## Leituras de analista

1. **ICP real vs declarado**: o que coincide, o que surpreende, o que o time persegue e não converte.
2. **Pipeline atual por tier**: quanto do valor aberto está em perfil C. É esforço comercial com baixa chance.
3. **Canal × perfil**: de onde vêm os perfis A (origem) e se a mídia está trazendo perfil C.
4. **Retenção**: perfis com win rate alto e churn alto (ganha fácil, perde depois).
5. **Desqualificação**: perfis C claros viram critério de saída cedo no funil (economia de tempo do time).

## Limites

- Correlação, não causalidade: atributos andam juntos (porte grande e ERP SAP, por exemplo).
- Viés de sobrevivência do CRM: só entra quem virou negócio. Perfis que nunca foram abordados não aparecem.
- Atributos mal preenchidos enviesam: diga a cobertura de cada campo.
