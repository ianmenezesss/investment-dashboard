# Auditoria da Fase 1.5

Escopo: código e arquivos locais do projeto, configuração de banco, autenticação, fronteira de demonstração e preparação para GitHub/Vercel/Render/Supabase. Nenhum segredo ou registro financeiro é reproduzido neste documento.

Atualização da Fase 1.6: [login Supabase implementado](supabase-auth.md), sem cadastro, com sessão por aba, recuperação confirmada por getUser, renovação, limpeza de cache por identidade e tratamento de 401. O backend continua recusando HS256 e exige assinatura assimétrica verificável por JWKS. O repositório Git agora existe, criado pelo proprietário após a Fase 1.5; não foi executado push nesta etapa. A constatação anterior de ausência de Git refere-se à auditoria inicial.

## Achados e tratamento

| Achado inicial | Tratamento |
| --- | --- |
| Ignore limitado a `.env`, sem variantes e exportações | Padrões para ambientes, segredos, backups, SQL, bancos, exports, logs, diretórios privados e ferramentas; exemplos fictícios preservados |
| Token compartilhado sem identidade de usuário | Preservado somente no modo local; modo Supabase opt-in valida assinatura JWT, expiração, issuer, audience, role e allowlist |
| Sem isolamento de registros | Coluna aditiva `owner_id`, filtros no servidor e RLS; registros legados continuam locais e nulos |
| Demonstração dependente de escolha manual na mesma interface privada | Build público sempre demonstrativo, handlers e HTTP bloqueiam rede/escrita, CSP sem conexões externas |
| Token nas chaves do cache | Removido das chaves; cancelamento e descarte do cache nas transições |
| Falhas de banco sem resposta controlada | Respostas genéricas 503, parâmetros SQL ocultos e timeout de conexão |
| Sem restrições explícitas de configuração de produção | Produção rejeita token local, CORS aberto, HTTP e banco sem TLS verificável; runtime exige papel restrito e RLS |
| Sem configuração de hospedagem e revisão automatizada | Modelos Vercel/Render, CI e scanner local sem envio a terceiros |
| Auditoria npm identificou avisos críticos no runner Vitest 3 e dependências transitivas | Runner atualizado para Vitest 5.0.5, compatível com Node 22.12+/24+; testes repetidos e auditoria final sem vulnerabilidades reportadas |

## Estado local e riscos remanescentes

- Não havia `.git` na pasta do projeto. Portanto não há histórico local nem arquivos rastreados a remover; não foi inicializado repositório ou executado push.
- `.env` existe e permanece privado. A verificação detectou senha local de PostgreSQL ainda igual ao placeholder de exemplo. A senha não foi exibida nem alterada para não desalinhar sua instalação. Escolha uma senha aleatória e faça uma rotação coordenada da credencial do papel PostgreSQL e de `.env` antes de qualquer uso remoto. Alterar só a variável do Compose não modifica a senha de um volume já inicializado.
- O Compose já restringia a porta a 127.0.0.1 e usava volume nomeado; essa configuração foi preservada. O papel padrão da imagem oficial é administrativo, aceitável apenas nessa instalação local. Em produção o backend rejeita papel privilegiado.
- Supabase não foi conectado, contas não foram criadas e autenticação remota não foi ativada. Os testes usam chaves criptográficas efêmeras e identidades fictícias.
- Não há rate limiting distribuído, revogação imediata de JWT, MFA ou auditoria de acessos implementados. Tokens assinados podem permanecer válidos até sua expiração; configurar duração curta e regras do provedor antes de ativar acesso remoto. A allowlist nega contas removidas dela no backend após atualização da configuração.
- O scanner reconhece assinaturas e segredos locais conhecidos nos candidatos ao Git e nos artefatos de build, mas não identifica todo dado pessoal ou dado financeiro arbitrário. Revise manualmente arquivos staged e alertas do GitHub antes de publicar.
- Não foi realizado pentest, inspeção de todo o filesystem, pesquisa em logs fora do projeto, varredura CVE completa de dependências nem inspeção de histórico remoto. Não se declara ausência absoluta de vulnerabilidades.

## Principais arquivos criados ou modificados

- `.gitignore`, `.env.example` e exemplos fictícios do frontend/backend.
- `backend/app/database.py`, `auth.py`, `access.py`, `main.py` e `models.py`.
- `backend/migrations/env.py` e `versions/002_ownership.py`.
- `backend/tests/conftest.py`, testes de autorização/isolamento, integração e runner PostgreSQL efêmero.
- `backend/scripts/check_local_database.py` e `scripts/audit_publication.py`.
- `frontend/src/App.tsx`, `main.tsx`, `api.ts`, `runtime.ts`, tipos Vite e testes de demonstração.
- Dependências/locks, configuração Vitest, `frontend/vercel.json`, `render.yaml`, CI e documentação.

A interface existente e os cálculos financeiros foram preservados. Nenhum CDB ou outra funcionalidade financeira nova foi incluído. Nenhum arquivo pessoal, tabela ou volume do banco pessoal foi removido. A migração é aditiva, e a verificação de persistência compara os registros originais em memória sem imprimir valores ou fingerprints.
