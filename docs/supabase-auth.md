# Supabase Auth — Fase 1.6

O frontend possui login por e-mail/senha, logout, recuperação de sessão, renovação automática e tratamento de expiração/401. A API reutiliza a validação JWT/JWKS, a allowlist e a RLS da Fase 1.5. Não há cadastro público nem migração de registros financeiros nesta etapa.

## Configurar o projeto Supabase existente

1. Nas configurações de Auth, desative novas inscrições públicas e mantenha apenas o usuário privado criado manualmente. A ausência de formulário de cadastro no app não substitui essa configuração no provedor.
2. Confirme que o projeto emite JWT com assinatura assimétrica **ES256 ou RS256**. O backend consulta somente as chaves públicas do JWKS em `/auth/v1/.well-known/jwks.json`, valida assinatura, expiração, issuer `${SUPABASE_URL}/auth/v1`, audience `authenticated` e role `authenticated`.
3. Se ainda usa **HS256**, não preencha um segredo de assinatura no frontend ou no código. Configure uma chave assimétrica seguindo a documentação do Supabase e faça novo login para obter um token emitido pela chave nova. Não rotacionamos chaves nem alteramos o projeto remoto nesta etapa. O backend rejeita HS256 explicitamente, sem fallback inseguro.
4. Localize a Project URL, a **Publishable Key** (`sb_publishable_...`) e o UUID do usuário autorizado. Esses valores não são a senha do PostgreSQL. Nunca usar `service_role`, `sb_secret_...`, chave privada ou senha como Publishable Key.

## Backend local: manter PostgreSQL Docker

Edite **somente as configurações de Auth** no `.env` da raiz; preserve `DATABASE_URL`, senha do PostgreSQL e o restante da configuração:

```dotenv
ENVIRONMENT=development
AUTH_MODE=supabase
SUPABASE_URL=https://YOUR-PROJECT.supabase.co
ALLOWED_USER_IDS=["UUID-DO-USUARIO-AUTORIZADO"]
CORS_ORIGIN=http://localhost:5173
```

Use URL sem barra final. `ALLOWED_USER_IDS` é uma lista JSON de UUIDs, não de e-mails. O backend não precisa de Publishable Key, senha de usuário, service role ou segredo de assinatura para verificar JWT assimétrico. `API_TOKEN` pode permanecer no `.env`, mas é ignorado enquanto `AUTH_MODE=supabase`.

Reinicie a API a partir de `backend`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Não há migração nova: `002` continua sendo o head. A identidade vem do Supabase, mas os dados financeiros continuam no PostgreSQL local. Não substitua a conexão local pela URL do banco Supabase para testar o login.

## Frontend local

A partir da raiz:

```powershell
Copy-Item frontend/.env.supabase.example frontend/.env.local
```

Se `.env.local` já existir, edite-o preservando suas configurações. Preencha nele os valores públicos do seu projeto:

```dotenv
VITE_PUBLIC_DEMO=false
VITE_APP_MODE=private
VITE_AUTH_MODE=supabase
VITE_SUPABASE_URL=https://YOUR-PROJECT.supabase.co
VITE_SUPABASE_PUBLISHABLE_KEY=sb_publishable_REPLACE_WITH_PUBLIC_KEY
VITE_API_BASE_URL=
```

`VITE_API_BASE_URL` vazio usa o proxy Vite `/api` → `http://127.0.0.1:8000`. Em um ambiente privado hospedado, precisa apontar para a origem HTTPS da API. As duas URLs Supabase (backend e frontend) precisam corresponder ao mesmo projeto.

```powershell
cd frontend
npm install
npm run dev
```

Abra http://localhost:5173 e entre com e-mail e senha do usuário que você já criou. Digite a senha somente no formulário; não use arquivos `.env` para senhas de usuários.

## Sessão e privacidade

- O SDK oficial usa `sessionStorage`, isolado por aba, em vez do localStorage padrão. Uma recarga recupera a sessão dessa aba; fechar a aba normalmente a descarta. Access/refresh tokens são sensíveis e acessíveis ao JavaScript da origem: mantenha proteção contra XSS e evite compartilhamento do perfil do navegador.
- A recuperação obtém a sessão pelo SDK e confirma o usuário com `getUser`. Os dados de storage não são tratados como autorização. A API sempre verifica o JWT criptograficamente, inclusive quando o frontend considera a sessão autenticada.
- O SDK renova tokens; `TOKEN_REFRESHED` atualiza o JWT enviado à API. Se expirar sem renovação ou se a API devolver 401, o app remove a sessão, cancela consultas, limpa o cache e volta ao login.
- O logout encerra a sessão atual (`scope: local`), remove o storage da aba e limpa a carteira da interface. Um JWT já emitido pode continuar válido no servidor até sua expiração; não é revogado instantaneamente apenas por logout.
- As consultas usam UUID de usuário em suas chaves, nunca tokens. Troca de identidade, logout e entrada em demonstração descartam o cache e cancelam consultas anteriores.
- A senha é enviada apenas ao Supabase via SDK/HTTPS, nunca ao FastAPI. Não há processamento de senha de usuário no PostgreSQL financeiro.

## Testar manualmente sem alterar registros existentes

1. Com backend e frontend configurados, entre com a conta autorizada. A API deve retornar 200 para leituras; nenhum registro é criado ao entrar.
2. É esperado que a carteira Supabase esteja vazia: registros locais antigos têm `owner_id IS NULL` e não pertencem ao UUID da conta. Não foram atribuídos automaticamente e não aparecem para usuários Supabase.
3. Recarregue a página: a sessão deve ser recuperada sem mostrar dados antes da validação. Clique em **Desconectar**: a carteira deve desaparecer e o formulário voltar.
4. Tente uma senha incorreta: deve aparecer um erro genérico, sem refletir senha ou mensagens internas do provedor.
5. Use uma conta fora da allowlist: o login no provedor pode ocorrer, mas a API deve negar acesso com 403. Não remova a autorização do backend para contornar esse resultado.
6. Clique em **Explorar demonstração**: a sessão privada é encerrada e o dashboard usa fixtures. Não há consultas à API privada durante a demonstração. Ao sair dela, o login volta.

Os testes automatizados cobrem expiração, token inválido, indisponibilidade de JWKS, ausência de autenticação, isolamento entre usuários e PostgreSQL local de teste. Não é necessário manipular JWTs reais ou compartilhar senhas para executar esses testes.

Para validar manualmente a navegação privada e os dados sem criar operações na conta real,
siga o checklist da [revisão final da Fase 3.0.4](phase-3.0.4-final-review.md). Use somente
dados fictícios ou um banco local descartável nos testes de compra, venda, aplicação, resgate,
REPLACE e VOID.

## Voltar ao token local de desenvolvimento

No `.env` da raiz, use `ENVIRONMENT=development` e `AUTH_MODE=local`; preserve seu `API_TOKEN` existente. No frontend, use `VITE_AUTH_MODE=local` e `VITE_PUBLIC_DEMO=false`, e reinicie ambos os servidores. Nesse modo só aparecem os registros locais sem proprietário. Não existe fallback automático para token se a validação Supabase falhar. Em produção, o backend recusa `AUTH_MODE=local` e o frontend sempre usa Supabase no modo privado.

## Demonstração e futuro deploy privado

O build de produção continua **demonstrativo por padrão**. `VITE_PUBLIC_DEMO=true` força demonstração em qualquer ambiente, sem instanciar cliente Supabase nem chamar API privada.

Para o build privado, configurar `VITE_APP_MODE=private`, `VITE_AUTH_MODE=supabase`, `VITE_PUBLIC_DEMO=false` e as URLs/chave públicas. O seletor `vercel.ts` mantém o modelo público `vercel.public.json` como padrão e preenche as duas origens HTTPS da CSP privada pelas variáveis do projeto. Não alterar os marcadores do modelo manualmente. Veja a [configuração exata do segundo projeto Vercel](private-frontend-production.md). Não foi executado deploy nesta preparação.

Antes de expor a API, mantenha os requisitos da Fase 1.5: papel restrito, TLS verificável, RLS, CORS HTTPS exato, backup, duração de sessão adequada e revisão de logs. O token local nunca é aceito como mecanismo de produção.

## Verificação desta entrega

O fluxo real do SDK foi implementado, mas as variáveis Supabase locais ainda não estavam preenchidas no momento da verificação. Portanto login contra seu projeto real, algoritmo efetivamente ativo nele e teste visual com sua conta continuam pendentes da configuração acima. Os testes usam SDK simulado e JWTs criptográficos efêmeros; não foram usados dados ou credenciais pessoais.

Arquivos principais: `frontend/src/auth/{supabase.ts,useAuth.ts,LoginPanel.tsx}`, integração em `App.tsx`, `api.ts`/`runtime.ts`, exemplos de ambiente, testes frontend/backend e ajuste explícito de HS256 em `backend/app/auth.py`. A autorização e os modelos financeiros existentes foram preservados.

Referências oficiais: [signInWithPassword](https://supabase.com/docs/reference/javascript/auth-signinwithpassword), [eventos de autenticação](https://supabase.com/docs/reference/javascript/auth-onauthstatechange), [getUser](https://supabase.com/docs/reference/javascript/auth-getuser) e [chaves de assinatura](https://supabase.com/docs/guides/auth/signing-keys).
