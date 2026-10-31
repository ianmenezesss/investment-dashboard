# Investment Dashboard

### Organize seus investimentos. Entenda seus números. Planeje com mais clareza.

Uma plataforma web para registrar e acompanhar investimentos em ações e renda fixa, consultar movimentações e explorar cenários — com cuidado para separar capital investido, estimativas de mercado e patrimônio informado.

**[Abrir a aplicação](https://investment-dashboard-pvd.vercel.app)** · **[Explorar a demonstração pública](https://investment-dashboard-pvd.vercel.app)** · **[Conhecer o plano do projeto](docs/INVESTMENT_DASHBOARD_MASTER_PLAN.md)**

`v1.0.0` · hotfix `v1.0.1` · React · TypeScript · FastAPI · PostgreSQL

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
- **Relatórios:** explore aportes, composição e movimentações com filtros; imprima pelo navegador ou salve como PDF.
- **Simulador:** compare cenários hipotéticos com aportes, prazos, taxas editáveis e inflação opcional.
- **Metas:** acompanhe progresso manual ou por custo/principal investido e planeje aportes. As metas ficam no navegador e não sincronizam entre dispositivos.

> Cotações e avaliações de mercado podem estar parciais ou indisponíveis. Fluxos e capital investido não são, por si só, patrimônio de mercado nem rentabilidade histórica.

### 🛡️ Demonstração e área privada

- **Demonstração pública:** usa dados fictícios e foi projetada para funcionar separada da API privada.
- **Área privada:** autenticação Supabase e autorização no backend; os registros são isolados por proprietário.
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

## Próximas versões

As etapas abaixo são **planejadas, não implementadas**:

- **v1.1 — Desempenho histórico:** estudar snapshots e dados confiáveis para acompanhar a evolução patrimonial e, quando houver cobertura suficiente, avaliar rentabilidade e benchmarks.
- **v1.2 — Assistente com IA:** explicar conceitos financeiros e orientar o uso das funcionalidades existentes, sem inventar recursos, enviar dados financeiros pessoais no MVP nem executar operações.
- **v2.0 — Acesso por convite:** avaliar expansão controlada para outras pessoas, preservando o isolamento entre carteiras.

O escopo, as dependências e as limitações estão no [Master Plan v1 → v2](docs/INVESTMENT_DASHBOARD_MASTER_PLAN.md).

## Conheça o projeto

Abra a [aplicação](https://investment-dashboard-pvd.vercel.app) para explorar a demonstração pública. O Investment Dashboard apresenta uma aplicação prática de desenvolvimento full-stack, segurança por proprietário, regras financeiras e visualização — com limites explícitos para dados que ainda não permitem conclusões históricas confiáveis.

**Documentação:** [Master Plan](docs/INVESTMENT_DASHBOARD_MASTER_PLAN.md) · [Arquitetura](docs/architecture.md) · [Segurança](docs/security-audit.md) · [Roadmap](docs/roadmap.md) · [Changelog](CHANGELOG.md)
