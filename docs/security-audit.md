# Auditoria de segurança — registro histórico da Fase 1.5

## Estado revisto para a preparação da v1.0 — 30/10/2026

O registro abaixo descreve a auditoria inicial da Fase 1.5; suas afirmações sobre ausência de Git, Supabase não conectado e funcionalidades planejadas são históricas e não representam o estado atual do produto.

- A `main` contém o fluxo privado Supabase Auth, a API FastAPI com autenticação e isolamento por proprietário/RLS, e a demonstração pública separada. O código e os testes locais foram revistos; nesta preparação, o GET público de `/health` do Render retornou HTTP 200 e a página Vercel privada documentada retornou HTTP 200 com CSP.
- Não foram fornecidas credenciais de usuário e não foram executados testes de login, acesso cruzado, gravações reais, endpoints financeiros autenticados ou logout em produção. Os resultados HTTP acima não validam esses fluxos.
- Não houve pentest, auditoria de configuração de painéis, leitura de dados do Supabase, nem verificação de configuração de backups/retention hospedada. Rate limiting distribuído, MFA e revogação imediata de JWT não estão comprovados nesta revisão.
- A demo precisa permanecer com sua CSP pública sem conexões privadas. A CSP observada no domínio Vercel privado permite as origens configuradas de Auth/API; confirme a CSP do domínio público separadamente antes da v1.0.

Esta seção atual é o resumo de segurança para lançamento. Os achados e comandos abaixo permanecem como registro histórico da fase inicial, não como evidência de validação da produção atual.

Atualização 1.6.3: confirmações nativas foram substituídas por um modal com semântica alertdialog, confirmação explícita e foco inicial em Cancelar. Os mesmos endpoints e filtros continuam protegendo operações privadas. O conjunto fictício foi ampliado sem sobrescrever documentos válidos antigos: o schema v1 é lido sem gravação, e o novo seed só entra por instalação limpa ou restauração confirmada. Não foram alterados autenticação, credenciais, banco pessoal ou volumes.

Atualização 1.6.2: a demonstração agora aceita operações fictícias persistidas exclusivamente na chave `investment-demo-portfolio`. `DemoRepository` não depende de API/Supabase; `PrivateRepository` não usa Storage. A criação/exclusão valida o histórico antes de persistir e a restauração toca somente a chave demonstrativa. Os testes confirmam ausência de chamadas financeiras HTTP na demonstração e ausência de acesso a localStorage no repositório privado. Isso não altera a autenticação privada existente.

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
