# Fase 5.0A — Navegação responsiva e identidade dinâmica

**Estado:** planejado; documentação não autoriza implementação. Esta etapa precede as fases 5.1–5.6 e prepara a experiência da aplicação para telas menores e para a expansão pessoal restrita. Mantém o custo obrigatório em zero.

## Objetivos

- Reduzir o espaço ocupado pela navegação lateral sem perder orientação ou acesso por teclado.
- Apresentar uma identidade útil baseada somente na sessão privada atualmente autenticada.
- Preservar a separação entre carteira privada, demonstração offline e futuras carteiras por convite.

## Escopo de navegação

### Desktop

- Estado expandido: rótulos, ícones e navegação completa.
- Estado recolhido: ícones com nomes acessíveis e tooltips visuais; tooltip não substitui o nome acessível.
- Botão de alternância com `aria-expanded`, `aria-controls` e estado anunciado.
- A preferência pode ser persistida localmente. A persistência deve ser opcional, sem sincronização de conta ou dados financeiros.

### Mobile

- Botão hambúrguer abre um drawer sobreposto e acessível, sem redimensionar ou sobrepor permanentemente o conteúdo.
- Fechamento pelo botão, seleção de rota e tecla Escape; devolver foco ao botão que abriu o drawer.
- Ao abrir, mover o foco para dentro do drawer e manter navegação por teclado nele; leitores de tela devem receber nome, estado e conteúdo coerentes.
- O conteúdo de fundo não deve permanecer interativo enquanto o drawer modal estiver aberto. Não bloquear zoom nem rolagem acessível.
- Mudanças de rota não devem descartar filtros ou estado de tela que a navegação atual já preserve.

## Escopo de identidade

- Obter nome e e-mail somente da sessão Supabase validada no frontend.
- Preferir um campo de nome de exibição presente em `user_metadata` (avaliar os campos realmente fornecidos pelo projeto); caso ausente, usar o prefixo do e-mail antes de `@`.
- Se nome e e-mail estiverem ausentes, mostrar um rótulo neutro, como “Investidor”, sem inventar identificador.
- Exibir a primeira letra do identificador de apresentação nos avatares existentes; normalizar visualmente sem alterar o valor de autorização.
- Truncar visualmente identificadores longos com `title`/texto acessível que permita consultar o rótulo inteiro sem quebrar o layout.
- Nunca usar nome, e-mail ou metadados do frontend para autorização. Backend continua usando `sub` validado, allowlist quando aplicável, `owner_id` e RLS.
- Ao trocar identidade, expirar ou encerrar sessão, limpar os dados privados em cache e a identidade anterior antes de mostrar outro usuário ou a tela anônima.
- A demo pública não lê nem herda sessão privada; deve continuar offline e independente dos dados de autenticação.

## Componentes e pontos de integração a revisar

- `frontend/src/App.tsx`: sidebar, navegação, layout responsivo, distinção das rotas demo e privadas.
- `frontend/src/auth/useAuth.ts`: ciclo de sessão, troca de identidade, expiração, logout e limpeza de cache existente.
- `frontend/src/auth/supabase.ts` e `frontend/src/auth/runtime.ts`: configuração e disponibilidade de Auth; nenhum segredo de servidor no bundle.
- `frontend/src/auth/LoginPanel.tsx`: manter fluxo de login/logout e feedback atuais.
- `frontend/src/style.css` e folhas de estilo dos componentes: breakpoints, drawer, foco visível, tooltips e prevenção de overflow.
- Testes de `App`, Auth, navegação e demo: adaptar ou ampliar os testes existentes antes de criar novos componentes. Um componente separado de sidebar só deve ser criado se simplificar o gerenciamento de foco e os testes.

## Critérios de aceite

1. Desktop expandido e recolhido funcionam; preferência persistida somente se a opção estiver habilitada.
2. Drawer mobile abre, fecha por botão, rota e Escape, devolve foco e não deixa controles de fundo acionáveis.
3. Navegação oferece foco visível, nomes acessíveis para ícones, ordem de tabulação lógica e estado da rota atual anunciado.
4. Layout é utilizável em larguras estreitas, zoom e conteúdo longo, sem conteúdo importante cortado ou sobreposição.
5. Nome de exibição tem precedência; fallback usa prefixo do e-mail; ausência de ambos gera rótulo neutro. Identificador longo não quebra a sidebar.
6. Logout, expiração e troca de usuário removem identidade anterior e dados privados; não há flash de informação da sessão anterior.
7. A demo segue independente do Supabase e da API privada, mesmo se variáveis privadas estiverem presentes no build.
8. Nenhum backend, política de autorização, migration ou dependência paga é necessário para esta etapa.

## Testes planejados

- Testes unitários para derivação de nome/avatar: metadados válidos, metadados ausentes, prefixo de e-mail, e-mail ausente e identificador longo.
- Testes de componente para expansão/recolhimento, tooltip e preferência local válida, ausente ou corrompida.
- Testes de interação mobile para abrir, Escape, fechar por rota, foco inicial, retorno de foco, tabulação e estado acessível; validar que o fundo não recebe interação enquanto modal.
- Testes de navegação preservando o estado previsto e de múltiplas larguras/zoom, complementados por revisão visual manual.
- Testes de Auth para logout, expiração e troca de `user.id`, afirmando que não resta nome ou dado em cache do usuário anterior.
- Testes da demo com Supabase indisponível e mocks de `fetch`, garantindo zero chamada privada e zero leitura da identidade privada.
- Suíte frontend completa, build de produção, revisão de acessibilidade por teclado/leitor de tela e `git diff --check`.

## Segurança, privacidade e custo

Esta proposta apenas altera apresentação no cliente. O identificador de autorização continua sendo o `sub` da sessão verificada pelo backend; metadados de perfil nunca substituem a validação de JWT ou a política de proprietário. Preferir os recursos já disponíveis no React, Supabase Auth e CSS, sem API paga, biblioteca obrigatória ou telemetria de identidade. Qualquer expansão multiusuário continua somente por convite ou aprovação explícita, sem acesso administrativo automático às carteiras.

## Dependências e não objetivos

- Não depende de fonte de cotações, migration ou dados financeiros novos.
- Não implementa simulador, metas, onboarding de convidados, cadastro público nem edição de perfil.
- As fases 5.1–5.6 e seus critérios permanecem como registrados no [roadmap](roadmap.md) e no [plano mestre da Fase 5](phase-5-master-plan.md).
- A etapa não resolve nem altera a disponibilidade dos históricos de preços 3.0.3, 4.1 ou 4.2.
