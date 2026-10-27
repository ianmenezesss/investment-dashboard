# Demonstração interativa — Fase 1.6.2

## Testar

```powershell
cd frontend
npm install
npm run dev
```

No ambiente privado local, abra http://localhost:5173/login e clique em **Explorar demonstração**. Também é possível abrir `/demo` diretamente, sem sessão. O build público inicia em demonstração. Não é necessário iniciar FastAPI ou PostgreSQL para usar a carteira fictícia.

1. Clique em **Nova operação**. Informe ticker em maiúsculas, compra/venda, data, quantidade, preço e taxas.
2. Experimente comprar `TEST4`, quantidade `10`, preço `20`, taxas `2`. Faça outra compra de `10` a `30`, sem taxas. O preço médio dessa posição deve ser `25,10`.
3. Venda `5` a `40`, taxa `1`: resultado realizado `73,50`, quantidade restante `15`, custo da posição `376,50`.
4. Tente vender acima da posição ou numa data anterior à compra. A operação deve ser recusada sem modificar a carteira.
5. Navegue por visão geral, ações e histórico; os cards, a composição e o gráfico são recalculados imediatamente. Use o botão de exclusão e confirme. Excluir uma compra que invalidaria vendas posteriores é bloqueado.
6. Atualize a página: suas operações demonstrativas continuam no mesmo navegador/origem.
7. Clique em **Restaurar demonstração** e confirme: somente a carteira fictícia retorna aos dados iniciais.

No ambiente privado, **Entrar na minha carteira** retorna à página de login. No endereço de demonstração pública, o botão informa que o login exige o ambiente privado, sem solicitar senha nem criar cliente Supabase. Não há URL privada inventada ou redirecionamento para um serviço não configurado.

## Persistência e falhas

Chave exclusiva: `investment-demo-portfolio`. O documento contém `kind: investment-demo`, versão `1` e somente os campos financeiros fictícios conhecidos. Nenhum token, e-mail, senha, identidade Supabase ou registro privado é armazenado nessa chave. O SDK privado continua usando seu sessionStorage separado.

O navegador/origem identifica a carteira local: pessoas que compartilham o mesmo perfil do navegador e a mesma origem compartilham a demonstração. Limpar dados do site ou mudar de navegador/origem perde a carteira fictícia. A atualização carrega o último documento salvo; sincronização simultânea entre abas não é implementada (a última gravação prevalece).

JSON inválido, versão desconhecida, IDs duplicados, valores inválidos ou histórico impossível carregam os fixtures iniciais com aviso. O conteúdo inválido é substituído ao restaurar ou salvar uma nova operação demonstrativa válida. Falha de quota ou bloqueio de storage mantém o uso em memória e informa que as mudanças durarão apenas a sessão.

O limite é de 10.000 operações demonstrativas, datas históricas até hoje, até 12 dígitos inteiros e 8 casas decimais. Os dados importados de storage também são validados e campos desconhecidos são descartados; não há importação de carteira privada.

## Arquitetura e cálculo

- `DemoRepository`: localStorage e estado observável apenas de demonstração; não importa fetch, Supabase ou repositório privado.
- `PrivateRepository`: HTTP autenticado existente, sem dependência de Storage. Queries privadas continuam desabilitadas na demonstração.
- `demo/finance.ts`: Decimal.js com 28 dígitos e ROUND_HALF_EVEN, mesmo contexto padrão do Decimal Python. Preserva ordem por data/ID, custo médio, taxas, custo removido e resultado realizado. Nenhuma função financeira privada foi alterada.
- `shared/finance-cases.json`: contratos fictícios usados por Vitest e Pytest para verificar equivalência entre os cálculos do frontend e as regras existentes do backend.

Compra adiciona `quantidade × preço + taxas` ao custo. Venda remove `quantidade vendida × preço médio anterior`; resultado realizado é `valor da venda − taxas − custo removido`. A validação cronológica ocorre sobre todo o histórico antes de persistir uma criação ou exclusão.

Os indicadores monetários são calculados em decimal e mantidos como strings. Os gráficos usam Number somente para visualização. O gráfico atual é de fluxo bruto de operações, não rentabilidade ou patrimônio a mercado. Preços são fictícios e patrimônio a mercado continua indisponível sem cotações identificadas. CDBs, metas e simulador foram retirados da navegação demonstrativa; suas páginas existentes continuam explicitamente planejadas.

## Validação

Executar `npm test`, `npm run build`, Pytest e a integração PostgreSQL temporária existente. Os testes cobrem criação/exclusão pela interface, recarga, restauração, custo médio, taxas, vendas inválidas, dados corrompidos e falhas de quota. Testes de rede verificam zero chamadas à API privada na demonstração; regressão de autenticação permanece ativa.

Não foram alterados DATABASE_URL, dados pessoais, volumes Docker ou o mecanismo de autenticação. O banco temporário de testes é independente do banco pessoal. Não houve deploy ou push.
