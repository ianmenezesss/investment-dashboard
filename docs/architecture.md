# Arquitetura e plano

Aplicação pessoal local, com frontend React/TypeScript/Vite e API FastAPI. PostgreSQL é a fonte dos registros reais; a demonstração existe apenas em memória no frontend. Não há dependência de localStorage nem integração financeira externa nesta fase.

Atualização da Fase 1.5: o build público é sempre uma demonstração sem rede privada. O acesso local por token foi preservado, e o backend ganhou um modo Supabase opt-in, autorização por proprietário e RLS. Veja [separação público/privado](demo-and-private.md), [auditoria](security-audit.md) e [deploy futuro](deployment.md). A integração externa não foi ativada.

Atualização da Fase 1.6: frontend privado com Supabase Auth implementado em `src/auth`, sem cadastro. Sessões por aba, recuperação via SDK/getUser, renovação, logout e tratamento de 401. A demonstração permanece padrão de produção, com opt-in explícito para o build privado. Configuração externa e homologação com a conta real ainda são necessárias; consulte [Supabase Auth](supabase-auth.md).

## Estrutura

```text
frontend/src/
  components/ui/   componentes de UI no padrão shadcn, Tailwind e Radix
  api.ts          contrato HTTP e tipos
  main.tsx        bootstrap React
  App.tsx         páginas e dashboard compartilhados
  runtime.ts      bloqueio da demonstração pública
  style.css       tema escuro e responsividade
backend/
  app/database.py configuração, engine e sessão SQLAlchemy
  app/models.py   modelo persistente
  app/finance.py  cálculo por custo médio sem dependência HTTP
  app/main.py     validação, autenticação e endpoints
  app/auth.py     token local ou JWT Supabase com allowlist
  app/access.py   identidade no contexto transacional de RLS
  migrations/    migrações Alembic versionadas
  tests/         testes das regras financeiras
compose.yaml     PostgreSQL local
```

## Fases e critérios

1. **Fundação:** dashboard responsivo, demonstração explícita, API protegida por token, compras e vendas de ações, histórico com busca e ordenação, exclusão confirmada, custo médio, exportação JSON e migração PostgreSQL. Verificar build, testes e inicialização. O gráfico representa fluxo de compras menos vendas, não evolução de mercado.
2. **Ações completas:** contas/corretoras, edição transacional com recálculo cronológico, dividendos/JCP, cotações manuais com fonte e timestamp e interfaces para provedores. Testar reinvestimentos sem dupla contagem. Separar usuário, ativo, conta, provento e cotação em tabelas próprias.
3. **Renda fixa:** contratos e lotes individuais, aportes, resgates parciais, prefixado/CDI/IPCA, tributação por lote e calendário adequado. Confirmar regras vigentes em fontes oficiais antes de implementá-las. Diferenciar saldo estimado e saldo bancário oficial.
4. **Medição:** snapshots patrimoniais, fluxos externos separados das negociações, benchmarks oficiais, XIRR e TWR quando houver dados suficientes. Rentabilidade não será calculada a partir de fluxo de compras/vendas.
5. **Planejamento:** simulador com premissas explícitas, metas, projeções e relatórios.
6. **Uso remoto:** autenticação de usuário, autorização por proprietário, HTTPS, política de backup/restauração testada e observabilidade antes de exposição pública.

Cada fase deve ser validada antes de expandir o escopo. Os links de CDBs, metas e simulador mostram o escopo planejado, sem simular funcionalidades implementadas.

## Decisões e dependências

- Backend Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, psycopg e Pytest.
- Frontend React, React Router, TanStack Query, Recharts, Lucide, Tailwind 4 e componentes locais no padrão shadcn/Radix.
- Valores entram como strings decimais, persistem em NUMERIC(20,8) e são calculados com Decimal. A API devolve valores monetários como strings. O frontend converte apenas para exibição e gráficos aproximados.
- O token é digitado e mantido apenas em memória no navegador. Não incluir segredos em VITE_* nem no repositório. Esta autenticação é provisória para uso local por uma pessoa e é rejeitada em produção. O backend preparado para Supabase valida identidade e filtra proprietário, mas ainda depende da configuração externa e de uma interface de login privada.
- As mutações bloqueiam a tabela de operações no PostgreSQL e validam a carteira cronológica inteira antes do commit. É uma decisão simples para um único usuário; evoluir para locks por carteira antes de multiusuário.
- Data e ID definem a ordem de operações do mesmo dia. Uma compra inserida depois de uma venda no mesmo dia não passa retroativamente à frente dela.
- Não há caixa contábil nesta fase. Compras não equivalem a aportes externos; receita de vendas não equivale a resgate. Por isso não são mostrados patrimônio consolidado, capital líquido aportado nem retorno percentual.
- Dividendos, CDBs, CDI, IPCA, Ibovespa e cotações não são inferidos ou inventados. Nenhuma credencial externa é necessária para a Fase 1.

## Fórmulas da Fase 1

Compra: custo adicionado = quantidade × preço + taxas.

Preço médio = custo remanescente / quantidade remanescente.

Venda: custo removido = quantidade vendida × preço médio anterior.

Resultado realizado = quantidade vendida × preço de venda − taxas − custo removido.

Após venda, deduzir quantidade e custo removido. Rejeitar venda sem posição suficiente na data; rejeitar exclusão de compra que invalidaria vendas posteriores.

O gráfico de fluxo acumulado soma compras e subtrai vendas por valor bruto. Taxas ficam fora desse gráfico e dentro dos cálculos contábeis. O gráfico não é uma curva de rentabilidade nem uma curva de patrimônio.

## Limites conhecidos

Sem edição, paginação ou importação nesta fase. A exportação JSON contém os registros operacionais; o backup completo é feito via pg_dump. Não há acesso remoto pronto para produção. A configuração de runtime requer .env e PostgreSQL funcionando.
