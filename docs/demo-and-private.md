# Demonstração pública e carteira privada

## Fronteiras

| Aspecto | Demonstração pública | Carteira privada local | Backend Supabase preparado |
| --- | --- | --- | --- |
| Dados | Fictícios, definidos no código | PostgreSQL local | PostgreSQL separado por proprietário |
| Autenticação | Nenhuma | Token em memória | JWT assimétrico + UUID autorizado |
| Leitura da API | Bloqueada em `request()` | Permitida com token | Permitida após validação no backend |
| Escrita | Bloqueada nos handlers e na camada HTTP | Compra/venda/exclusão autenticadas | Operações limitadas ao proprietário |
| Banco | Nenhum | Registros `owner_id IS NULL` | Registros com UUID do usuário |
| Exportação | Apenas fixtures fictícias | Registros do usuário local | Registros do usuário autenticado |

Desde a Fase 1.6, o frontend privado possui login Supabase. Produção permanece demonstrativa por padrão; somente `VITE_APP_MODE=private` habilita explicitamente a interface privada. `VITE_PUBLIC_DEMO=true` sempre prevalece, sem criar cliente Supabase. O arquivo `vercel.json` continua exclusivo da demonstração, com CSP `connect-src 'none'`. O modelo privado é separado. Veja [configuração de Auth](supabase-auth.md).

O modo local via `npm run dev` continua oferecendo token e demonstração com `VITE_AUTH_MODE=local`. O modo `supabase` usa login e sessão em sessionStorage por aba. A mudança de modo cancela requisições, descarta o cache e encerra a sessão Supabase ao entrar na demonstração. As chaves das consultas contêm identidade do usuário, nunca tokens. Nenhuma sessão privada é salva em localStorage ou cookies.

Os mesmos componentes renderizam os dois conjuntos de dados. Não há cópia de registros pessoais nos fixtures. Os valores de ITUB4, BBAS3 e B3SA3 da demonstração são inventados e não devem ser apresentados como cotações reais. O histórico demonstrativo é de operações de compra; não existe um livro de aportes externos implementado.

## Autorização no servidor

`authenticate` valida identidade; `private_db` configura o contexto transacional de RLS. Leituras, exportações e exclusões filtram `owner_id` no SQL. A criação obtém o proprietário da identidade verificada, jamais do JSON enviado pelo cliente. Tentativas de excluir uma operação de outro usuário recebem 404, sem revelar sua existência.

A migração `002` acrescenta `owner_id` nulo aos registros legados sem atribuí-los a uma identidade externa. O modo local acessa apenas os registros nulos; o modo Supabase acessa apenas registros com o UUID autenticado. Não há associação automática do patrimônio local a uma conta Supabase.

A política RLS usa `app.user_id` e `app.auth_mode`, definidos por `set_config(..., true)` em cada transação da API. Essa política pressupõe uma conexão de banco confiável e não permite clientes executarem SQL arbitrário. O papel de runtime deve ter apenas DML e acesso à sequência, sem propriedade, superusuário ou BYPASSRLS. As políticas não concedem acesso financeiro direto via Supabase REST ao navegador; não use a chave administrativa para contornar isso.

## Antes de abrir uma interface privada na internet

Configurar Supabase Auth, desativar inscrições públicas, criar contas manualmente, revisar allowlist, configurar papel restrito/TLS, validar RLS e homologar o login implementado. Apenas então avaliar a migração explícita dos registros locais, com backup e conferência. O build público permanece independente. Para testar localmente a identidade Supabase, manter o PostgreSQL Docker atual e sua DATABASE_URL.

O teste frontend verifica navegação sem login, ausência do campo de token, bloqueio de escrita e zero chamadas HTTP mesmo quando a API está indisponível. Os testes backend verificam assinatura, expiração, issuer, audience, role, allowlist e separação de carteiras. A integração PostgreSQL verifica a política RLS com um papel não privilegiado.
