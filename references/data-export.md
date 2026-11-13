# Como obter os dados / Getting the data

A skill aceita CSV ou XLSX de qualquer CRM. Colunas mínimas: **data de criação**, **valor** e **status ou etapa**.
Recomendadas: data de fechamento, dono, origem, motivo de perda, segmento, porte, região. O `normalize.py` reconhece
os nomes padrão em português e inglês; se algo não for detectado, crie `mapa.json` com `{"campo": "Nome da coluna"}`
(campos: id, name, created, closed, stage, status, amount, owner, source, loss_reason, segment, company_size,
region, company, pipeline) e rode de novo com `--map mapa.json`.

## Com conector (preferido quando existir na sessão)

- **HubSpot**: use a busca de objetos de CRM para negócios (deals) com as propriedades `dealname`, `createdate`,
  `closedate`, `dealstage`, `amount`, `hubspot_owner_id`, `hs_analytics_source`, `closed_lost_reason`, `pipeline`
  e os campos `hs_date_entered_<etapa>` para o histórico. Pagine até o fim e salve como CSV antes de analisar.
  Traduza `dealstage` (ID interno) para o rótulo da etapa com o esquema do pipeline.
- **Apollo / outros**: mesma lógica, salve tudo em CSV primeiro. Nunca analise página por página na conversa.

## Por export manual

| CRM | Caminho |
|---|---|
| HubSpot | CRM → Negócios → visualização "Todos" → Exportar (inclua todas as propriedades) |
| Pipedrive | Negócios → visualização em lista → ⋯ → Exportar resultados do filtro |
| RD Station CRM | Negociações → Exportar (planilha) |
| Salesforce | Relatório de Oportunidades com Created Date, Close Date, Stage, Amount, Owner, Lead Source, Loss Reason → Exportar |
| Ploomes / Agendor / planilha | Exporte negócios com as colunas acima |

## Histórico de etapas (opcional, recomendado)

CSV com uma linha por mudança de etapa: `negócio, etapa, data de entrada`. HubSpot: exporte as propriedades
"Date entered [etapa]" e converta para linhas (o Claude faz isso). Salesforce: Opportunity History.

## Status

Se o export não tiver coluna de status, o status vem da etapa ("Ganho", "Closed Won", "Perdido"...). Etapas com nomes
próprios: `--won-stages "Contrato assinado" --lost-stages "Descartado,Sem fit"`. Valor em MRR: `--monthly-amount 12`
para analisar em ACV.

## Privacidade

O export tem dados de clientes. Trabalhe só na pasta de trabalho da sessão, não publique o CSV e não coloque nomes de
pessoas de contato no relatório (nome do negócio e dono interno bastam).
