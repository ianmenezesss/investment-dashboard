# Investment Dashboard

### Organize seus investimentos. Entenda seus números. Planeje com mais clareza.

Uma plataforma web para registrar e acompanhar investimentos em ações e renda fixa, consultar movimentações e explorar cenários — com cuidado para separar capital investido, estimativas de mercado e patrimônio informado.

**[Abrir a aplicação](https://investment-dashboard-pvd.vercel.app)** · **[Explorar a demonstração pública](https://investment-dashboard-pvd.vercel.app)** · **[Conhecer o roadmap](docs/INVESTMENT_DASHBOARD_V2_ROADMAP.md)**

`v2.0.0` publicada · `v3.0.0` candidata local validada, ainda não publicada · React · TypeScript · FastAPI · PostgreSQL

---

## Uma visão mais organizada da carteira

O projeto nasceu para reunir registros de investimentos e tornar suas bases mais fáceis de entender. Em vez de apresentar todo valor como “rentabilidade”, o dashboard distingue operações, fluxos financeiros, custo/principal e avaliações que dependem de dados disponíveis.

É um projeto pessoal e de portfólio que combina desenvolvimento full-stack, regras financeiras, autenticação e visualização de dados em uma experiência responsiva em português.

## O que você encontra

### 📊 Gestão de investimentos

- **Ações:** registre compras e vendas; acompanhe posições pelo custo médio, incluindo taxas registradas e resultado realizado.
- **Renda fixa:** organize aplicações e resgates de CDB por contrato, com principal e estimativas apresentados sob suas premissas.
- **Movimentações:** consulte operações e eventos financeiros manuais, como aportes, retiradas, dividendos e JCP, em um Histórico filtrável.

### 🔎 Análise e planejamento

- **Dashboard e composição:** visualize posições, fluxos registrados e bases de composição com indicações de cobertura.
- **Histórico de ações:** quando habilitado no backend, consulte preços ajustados da Brapi Free; períodos além de três meses aparecem como parciais. Isso não reconstrói o patrimônio histórico da carteira.
- **Evolução patrimonial:** registre observações datadas com fonte; CDBs só entram no total quando todos os contratos ativos estão cobertos exatamente na data. Não infere datas ou retorno.
- **Relatórios:** explore aportes, composição, movimentações e proventos manuais com filtros; imprima pelo navegador ou salve como PDF.
- **Simulador:** compare cenários hipotéticos com aportes, prazos, taxas editáveis e inflação opcional.
- **Metas:** acompanhe progresso manual ou por custo/principal investido e planeje aportes. As metas ficam no navegador e não sincronizam entre dispositivos.

> Cotações e avaliações de mercado podem estar parciais ou indisponíveis. Fluxos e capital investido não são, por si só, patrimônio de mercado nem rentabilidade histórica.

### 🛡️ Demonstração e área privada

- **Demonstração pública:** usa dados fictícios e foi projetada para funcionar separada da API privada.
- **Área privada:** autenticação Supabase e autorização no backend; os registros são isolados por proprietário.
- **Íris:** assistente opcional de educação financeira, disponível somente na área privada autenticada. Combina conhecimento estático com o nome permitido da tela atual; não recebe valores, posições, operações, filtros nem outros dados da carteira. As perguntas são enviadas à Groq; não inclua informações pessoais ou financeiras.
- **Privacidade:** a demonstração não usa a carteira privada. O produto não oferece cadastro público irrestrito.

## Prévia do produto

Não há capturas de tela reais versionadas neste repositório neste momento. A seção está reservada para imagens do dashboard e de suas análises em `docs/assets/screenshots/`, após revisão para remover dados pessoais. Até lá, [explore a demonstração pública](https://investment-dashboard-pvd.vercel.app).

## Tecnologias e engenharia

| Área | Stack |
|---|---|
| Interface | React 19, TypeScript, Vite, Tailwind CSS, Radix UI, Recharts e TanStack Query |
| API e dados | Python 3.12+, FastAPI, SQLAlchemy, Alembic e PostgreSQL |
| Identidade e hospedagem | Supabase Auth, Vercel e Render |
| Qualidade | Vitest, Pytest e GitHub Actions |

O backend concentra as regras financeiras e usa `Decimal` para cálculos monetários. A API valida a identidade, filtra dados por proprietário e trabalha com RLS no PostgreSQL. A rotina de CI executa testes de backend e frontend, integração em PostgreSQL descartável, build e auditoria de dependências.

Na área privada, **Exportar meus dados** gera um JSON com os dados financeiros da conta, metadados básicos de membership e metas locais deste navegador. Na demonstração, a exportação contém apenas as operações fictícias. A exportação não substitui um backup do banco.

## Estado das versões

`v2.0.0` é a última versão publicada. A candidata local `v3.0.0` acrescenta acesso por convite, carteiras isoladas por proprietário, exclusão de conta retomável e loader administrativo explícito para dados inteiramente fictícios. A validação local cobre backend, frontend, build e PostgreSQL descartável até a migration 012. A v3.0 ainda não foi publicada; migration e configuração de produção seguem o checklist operacional, sem cadastro público.

## Conheça o projeto

Abra a [aplicação](https://investment-dashboard-pvd.vercel.app) para explorar a demonstração pública. O Investment Dashboard apresenta uma aplicação prática de desenvolvimento full-stack, segurança por proprietário, regras financeiras e visualização — com limites explícitos para dados que ainda não permitem conclusões históricas confiáveis.

**Documentação:** [Master Plan](docs/INVESTMENT_DASHBOARD_MASTER_PLAN.md) · [Análise financeira v2.0](docs/v2.0-financial-analysis.md) · [Arquitetura](docs/architecture.md) · [Segurança](docs/security-and-invitations.md) · [Checklist v3.0](docs/v3-launch-checklist.md) · [Changelog](CHANGELOG.md)
