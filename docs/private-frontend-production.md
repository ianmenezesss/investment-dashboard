# Fase 1.8.1 — frontend privado com API Render

O código existente já usa `VITE_API_BASE_URL` em `src/runtime.ts` e `src/api.ts`.
O cliente acrescenta `/api/operations`, `/api/dashboard` etc., enviando o access token
Supabase como Bearer, sem cookies e sem cache HTTP. Não acrescentar `/api` à variável.
Nenhuma alteração no fluxo de autenticação, backend ou demo é necessária para essa integração.

## Variáveis do projeto privado Vercel

Root Directory: `frontend`; framework Vite; Build Command `npm run build`; Output Directory `dist`.
Preparar um projeto privado separado do projeto da demonstração. Não trocar as variáveis ou
os headers do projeto público existente.

| Variável | Valor |
| --- | --- |
| VITE_PUBLIC_DEMO | false |
| VITE_APP_MODE | private |
| VITE_AUTH_MODE | supabase |
| VITE_API_BASE_URL | https://investment-dashboard-3ogz.onrender.com |
| VITE_SUPABASE_URL | Origem HTTPS real do projeto Supabase usado pelo backend |
| VITE_SUPABASE_PUBLISHABLE_KEY | Publishable Key pública desse projeto, iniciada por sb_publishable_ |

O exemplo `frontend/.env.private.example` não contém credenciais reais. Na Vercel, configurar
os valores diretamente para Production; Preview somente se a origem também estiver autorizada.
Não colocar DATABASE_URL, API_TOKEN, senha, service_role, sb_secret_ ou chave privada em VITE_*.
Os valores VITE_* fazem parte do JavaScript público. Alterações exigem novo build.

O Vite lê `.env*` da pasta frontend, não o `.env` raiz do backend. Variáveis do processo de build
têm precedência sobre os arquivos. `.env.local` é exclusivamente local e não configura a Vercel.
`VITE_PUBLIC_DEMO=true` sempre prevalece; sem `VITE_APP_MODE=private`, produção permanece demo.
No desenvolvimento, API base vazia usa o proxy local; no build hospedado esse proxy não existe.
Uma base vazia na Vercel faria chamadas à própria Vercel, em vez do Render.

## Seleção automática da configuração para dois projetos

Os dois projetos podem apontar ao mesmo repositório e branch, com Root Directory `frontend`.
O único arquivo de configuração ativo é `frontend/vercel.ts`, mecanismo programático oficial
da Vercel. Não manter um `frontend/vercel.json` junto dele: a Vercel aceita somente um arquivo ativo.
O arquivo público anterior foi renomeado para `vercel.public.json`, com conteúdo idêntico.

- Sem `VITE_APP_MODE=private`, usa integralmente `vercel.public.json`, incluindo `connect-src 'none'`.
- `VITE_PUBLIC_DEMO=true` sempre seleciona a configuração pública, mesmo com modo private.
- No projeto privado, exige `VITE_PUBLIC_DEMO=false`, `VITE_AUTH_MODE=supabase` e origens HTTPS
  válidas em `VITE_API_BASE_URL` e `VITE_SUPABASE_URL`; valores ausentes ou inválidos interrompem
  a configuração, sem registrar seus conteúdos.
- A CSP privada vem de `vercel.private.example.json`, substituindo os dois marcadores pelas
  origens dessas variáveis. Não editar manualmente os marcadores do modelo. Não há curinga.
- `connect-src` privado permite somente `'self'`, a origem Supabase Auth e a origem Render.
  O login por senha utiliza HTTPS; não há Realtime/WebSocket neste fluxo.
- Headers de segurança e rewrite SPA permanecem presentes nos dois modos. Nenhuma chave entra na CSP.

A seleção ocorre antes do build, não dentro de `npm run build`. Não usar um Install/Build Command
para copiar outro arquivo por cima de vercel.json: isso não é uma seleção confiável da configuração.
O seletor não lê `.env.local`: configure as seis variáveis no painel do projeto privado.

No novo projeto Vercel usar exatamente:

| Configuração | Valor |
| --- | --- |
| Git Repository / Production Branch | Mesmo repositório / branch utilizado pelo projeto público |
| Root Directory | frontend |
| Framework Preset | Vite |
| Install Command | npm ci |
| Build Command | npm run build |
| Output Directory | dist |
| Variáveis | As seis da tabela anterior, no ambiente Production |

Não alterar o projeto público. Não habilitar modo privado em Preview sem conferir CORS e o destino
dos dados; por padrão, ambientes sem as variáveis privadas continuam demo.

Para enviar a implementação ao GitHub, incluir a remoção de `frontend/vercel.json`, a adição de
`frontend/vercel.public.json`, `frontend/vercel.ts`, ambos os arquivos de `frontend/deployment/`,
`frontend/package.json`, `frontend/package-lock.json` e `frontend/tsconfig.json` (tipagem Node
e checagem da configuração no build), esta documentação e as atualizações das referências nos demais documentos. Incluir também os
arquivos pendentes da Fase 1.8.1: `.gitignore`, `frontend/.env.private.example` e
`frontend/src/api.production.test.ts`. Não enviar `.env.local`, `.env`, node_modules, dist ou .vercel.
Nenhum commit, push, configuração de painel ou publicação foi executado pelo Codex.

## Dependências externas a confirmar manualmente

- No Render, CORS_ORIGIN precisa coincidir com a origem HTTPS final do frontend privado,
  sem caminho ou barra final. Não foi alterado nesta fase. O código aceita uma origem exata.
- SUPABASE_URL do backend e VITE_SUPABASE_URL devem apontar ao mesmo projeto.
- O UUID da conta precisa estar em ALLOWED_USER_IDS do backend.
- Configurar URLs de redirecionamento no Supabase somente se um fluxo utilizado as exigir.
  O login atual é por e-mail/senha, com detectSessionInUrl desativado, sem OAuth/cadastro público.

## Verificação local e aceitação futura

Na pasta frontend, executar `npm test` e `npm run build`. Para validar explicitamente o bundle
privado sem editar `.env.local`, usar uma janela PowerShell dedicada, informando os valores
públicos reais somente localmente:

```powershell
Set-Location 'C:\Users\IAN\ProjetosVSCode\investment-dashboard\frontend'
$env:VITE_APP_MODE = 'private'
$env:VITE_PUBLIC_DEMO = 'false'
$env:VITE_AUTH_MODE = 'supabase'
$env:VITE_API_BASE_URL = 'https://investment-dashboard-3ogz.onrender.com'
$env:VITE_SUPABASE_URL = Read-Host 'Project URL pública real'
$env:VITE_SUPABASE_PUBLISHABLE_KEY = Read-Host 'Publishable Key pública real'
npm run build
```

Fechar a janela ao terminar. `vite preview` testa o bundle, mas não reproduz headers Vercel.
Os testes de HTTP usam fetch simulado e não comprovam autenticação real no Supabase.

Após uma publicação futura autorizada: confirmar os headers CSP no navegador; sem sessão,
somente login e nenhuma chamada financeira; login real autorizado retorna dados via Render;
refresh restaura sessão; logout remove a carteira; 401 encerra sessão e 403 informa autorização
negada. Na rota demo, nenhuma chamada privada deve ocorrer. Não criar operações de teste reais.

Nesta fase não foram realizados deploy, push, mudanças em painéis, consultas autenticadas remotas,
alterações no backend, migrações, RLS ou banco.

Referências: [Vite env](https://vite.dev/guide/env-and-mode),
[Vercel env](https://vercel.com/docs/environment-variables) e
[configuração programática Vercel](https://vercel.com/docs/project-configuration/vercel-ts).
