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

O frontend de produção desta fase é sempre público e demonstrativo. Não contém login privado, URL obrigatória de API ou qualquer credencial. O arquivo `vercel.json` acrescenta CSP com `connect-src 'none'`, defesa adicional para impedir rede nesse artefato.

O modo local via `npm run dev` continua oferecendo token e demonstração. A mudança de modo cancela requisições, descarta o cache e remove o token da memória do estado. As chaves das consultas não contêm tokens. Nenhuma sessão privada é salva em localStorage ou cookies.

Os mesmos componentes renderizam os dois conjuntos de dados. Não há cópia de registros pessoais nos fixtures. Os valores de ITUB4, BBAS3 e B3SA3 da demonstração são inventados e não devem ser apresentados como cotações reais. O histórico demonstrativo é de operações de compra; não existe um livro de aportes externos implementado.

## Autorização no servidor

`authenticate` valida identidade; `private_db` configura o contexto transacional de RLS. Leituras, exportações e exclusões filtram `owner_id` no SQL. A criação obtém o proprietário da identidade verificada, jamais do JSON enviado pelo cliente. Tentativas de excluir uma operação de outro usuário recebem 404, sem revelar sua existência.

A migração `002` acrescenta `owner_id` nulo aos registros legados sem atribuí-los a uma identidade externa. O modo local acessa apenas os registros nulos; o modo Supabase acessa apenas registros com o UUID autenticado. Não há associação automática do patrimônio local a uma conta Supabase.

A política RLS usa `app.user_id` e `app.auth_mode`, definidos por `set_config(..., true)` em cada transação da API. Essa política pressupõe uma conexão de banco confiável e não permite clientes executarem SQL arbitrário. O papel de runtime deve ter apenas DML e acesso à sequência, sem propriedade, superusuário ou BYPASSRLS. As políticas não concedem acesso financeiro direto via Supabase REST ao navegador; não use a chave administrativa para contornar isso.

## Antes de abrir uma interface privada na internet

Configurar Supabase Auth, desativar inscrições públicas, criar contas manualmente, revisar allowlist, migrar um banco separado, configurar papel restrito, validar RLS e implementar login por e-mail/senha numa interface privada separada. Apenas então avaliar a migração explícita dos registros locais, com backup e conferência. O build público permanece independente.

O teste frontend verifica navegação sem login, ausência do campo de token, bloqueio de escrita e zero chamadas HTTP mesmo quando a API está indisponível. Os testes backend verificam assinatura, expiração, issuer, audience, role, allowlist e separação de carteiras. A integração PostgreSQL verifica a política RLS com um papel não privilegiado.
