# Investment Dashboard v1.0.0 — notas de lançamento

> Registro das notas da versão publicada. As validações abaixo descrevem a evidência registrada para o candidato v1.0.0; o hotfix v1.0.1 está no `CHANGELOG.md`. O status atual dos painéis Vercel/Render não foi revalidado nesta atualização.

O Investment Dashboard v1.0.0 reúne acompanhamento manual de investimentos em ações e renda fixa em português, com uma demonstração pública baseada em dados fictícios e uma área privada autenticada.

## Principais recursos

- Registro e acompanhamento de compras/vendas de ações, posições e operações de renda fixa CDB.
- Eventos manuais de aportes, retiradas, dividendos e JCP, com histórico de revisões.
- Histórico filtrável e visão de composição/fluxos com bases e cobertura identificadas.
- Relatórios privados com filtros e impressão para PDF pelo navegador.
- Simulador local com cenários, aportes, prazos e premissas editáveis.
- Metas financeiras por identidade no armazenamento local do navegador, com progresso manual ou custo/principal investido e projeções hipotéticas.
- Demonstração sem conexão à carteira privada e sem gravações financeiras externas.

## Segurança e tratamento financeiro

- A área privada usa Supabase Auth, API FastAPI e isolamento por proprietário/RLS no PostgreSQL.
- A demonstração usa somente dados fictícios e permanece separada dos serviços privados.
- Custo investido, principal, patrimônio informado, estimativas de mercado e projeções têm rótulos distintos. Simulações não são promessa de rentabilidade.
- Metas permanecem no navegador e não sincronizam entre dispositivos.
- Foi gerado um único backup manual cifrado fora do repositório. O procedimento não agenda cópias e não restaura Auth, Storage binário ou configurações externas.

## Tecnologias

React 19, TypeScript, Vite, Tailwind, Radix UI, Recharts, TanStack Query, Supabase Auth, Python 3.12, FastAPI, SQLAlchemy, Alembic e PostgreSQL 17.

## Validação desta candidata

- Vitest: 217 testes aprovados em 28 arquivos.
- Build de produção TypeScript/Vite: aprovado.
- `npm audit`: nenhuma vulnerabilidade conhecida reportada.
- Pytest: 382 aprovados e 1 teste de integração PostgreSQL opt-in ignorado; aviso de depreciação `TestClient`/httpx.
- PostgreSQL 17 descartável: migrations até 009 e round-trip sintético de backup/restauração com eventos, policies/RLS, grants e isolamento aprovados.
- Smoke GET: as rotas SPA `/`, `/login` e `/metas` responderam 200; `/health` do backend respondeu 200. Esses GETs não testam autenticação; os fluxos principais privados foram confirmados manualmente pelo proprietário, conforme o item abaixo.
- O proprietário confirmou manualmente login, dashboard/navegação, Histórico, Relatórios, Simulador, Metas, logout, demonstração pública e layout geral em desktop/celular, sem erro observado. Esses relatos não equivalem a teste independente de isolamento entre contas, operações detalhadas ou Network/CSP.

## Limitações conhecidas

- Desempenho patrimonial histórico e benchmarks (Fase 5.6) não fazem parte desta versão; os dados disponíveis não sustentam um histórico completo ou TWR/XIRR confiável.
- Cotações e valuation podem estar parciais ou indisponíveis; cotações atuais não são usadas como preços históricos.
- Metas locais não são transferidas entre dispositivos ou perfis do navegador.
- Um único backup é apenas um ponto de recuperação. O restore do artefato real em PostgreSQL descartável ainda não foi ensaiado; Auth, Storage binário, roles globais, configurações externas e alterações posteriores ficam fora do dump `public`.
- Revisão geral desktop/celular e fluxos principais foram confirmados pelo proprietário. Isolamento com duas contas de produção, Network/CSP detalhado e SHAs implantados ainda não foram confirmados independentemente.
