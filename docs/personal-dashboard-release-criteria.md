# Critérios de release e conclusão do dashboard pessoal

Este documento separa três marcos: release v4.0.0, release v5.0.0 e conclusão/estabilização do produto pessoal. Uma tag de versão não significa que todas as propostas históricas foram implementadas.

## Release v4.0.0

**Escopo recomendado:** resumo financeiro atual 4.3A, mais as funcionalidades 4.1/4.2 com disponibilidade corretamente representada.

Pré-requisitos:
- testes de regras de custo médio, fees, CDB principal e REPLACE/VOID;
- autenticação, autorização por proprietário e RLS testadas;
- flags históricas falsas por padrão; sem requisições históricas quando desligadas;
- cotações pontuais sem regressão;
- nenhum fluxo é chamado de rentabilidade; nenhum total parcial é chamado de patrimônio;
- estado ausente/partial/stale/unavailable em APIs e UI;
- demo offline, sem conexão com conta privada;
- suite frontend/backend, integração PostgreSQL descartável relevante, build e diff checks;
- revisão de variáveis e configuração pública/privada, compatibilidade do banco e ausência de migration não aprovada;
- backup recuperável e instrução de rollback verificáveis;
- documentação e CHANGELOG descrevem somente entregas reais.

Não é pré-requisito ter provedor histórico pago ou gratuito aprovado. Enquanto não houver, a 3.0.3 e dados reais de 4.1/4.2 ficam indisponíveis explicitamente.

## Release v5.0.0

Definir antes do início quais das fases 5.1–5.6 entram na release. Requisitos:
- fórmulas e semântica de cada evento documentadas e testadas;
- simulações rotuladas como cenários hipotéticos;
- metas só exibem progresso quando a base é conhecida;
- importação sempre revisável antes de gravar;
- migrations aditivas testadas em banco descartável e compatíveis com rollback/procedimento seguro;
- privacidade, auth, owner_id e RLS mantidos;
- nenhum recurso bloqueado por fonte aparece ativo;
- versão, CHANGELOG, roadmap, CI e roteiro de verificação conferidos.

## Estabilidade/conclusão do produto pessoal

### Funcional
- fluxo de login/logout/renovação e recuperação de sessão testados;
- operações de ações e CDBs cobertas, incluindo revisões e resgates;
- composição/resultado diferencia bases, estimativas, observações e indisponibilidade;
- histórico de operações privado, exportação e estados vazios/erro compreensíveis;
- pendências de dados históricos sem preço inventado.
- simulador/metas são opcionais para estabilidade de release v4; para declarar v5 completo, aplicar o escopo v5 que for aprovado.

### Financeiro e dados
- fórmulas reconciliáveis com casos de teste por Decimal;
- taxas contabilizadas exatamente uma vez;
- compras, vendas, aplicações, principal resgatado, proventos e fluxos externos têm semântica distinta;
- valores de mercado mostram fonte, data e cobertura;
- posições manuais não viram lotes fictícios; campos desconhecidos continuam null;
- operações pessoais antigas só são vinculadas a owner após processo separado, backup e autorização.

### Segurança
- Supabase JWT/JWKS, allowlist, owner_id/RLS, papel runtime sem privilégio administrativo;
- segredo não exposto em frontend, Git, logs ou outputs;
- CORS exato, HTTPS/TLS, autorização por endpoint e exportação;
- conta sem acesso tem 401/403; duas identidades isoladas em testes PostgreSQL;
- revisar dependências, CSP, XSS, autenticação de sessão e exposição de erros.

### Operação e recuperação
- backup automático ou procedimento local gratuito conforme ambiente, com local de retenção protegido;
- teste de restauração em clone descartável; documentar RPO/RTO realista, sem prometer disponibilidade;
- processo de migration e rollback de aplicação; backup antes de schema change;
- logs sem token, senha, DSN nem conteúdo financeiro; health check sem dados pessoais;
- alertas e limites compatíveis com recursos gratuitos; procedimento em falha/suspensão.

### Performance e UX
- build e testes repetíveis; ausência de erros bloqueantes no console;
- consultas paginadas/limitadas onde volume cresce; timeout, cache e cancelamento;
- layout desktop/mobile, teclado/leitor de tela e datas/moedas pt-BR;
- demonstração pública funciona sem backend privado; telas privadas não vazam em cache.

### Políticas e documentação
- origem/licença/limites dos provedores documentados; recurso externo pode ser desligado;
- política de retenção, exportação e remoção de dados definida para o próprio usuário;
- tutorial local, variáveis obrigatórias, troubleshooting e passos de restauração;
- pendências 3.0.3/4.1/4.2 continuem visíveis como bloqueadas se não aprovadas.

A conclusão pessoal não exige uma fonte histórica gratuita se nenhuma fonte permitida servir. Pode ser declarada estável com limites documentados, sem prometer métricas indisponíveis.

## Publicação e rollback

1. validar local e CI, revisar diff/segredos e configurar backup;
2. homologar em banco descartável com papel runtime restrito;
3. publicar frontend/API em ordem coordenada com migrations somente se aprovadas e necessárias;
4. confirmar login e proprietário autorizado sem registrar dados reais de teste;
5. manter deploy manual e versão anterior pronta para rollback.
6. rollback de app não reverte schema automaticamente. Se houve migration, restaurar dados/schema conforme procedimento ensaiado; não fazer downgrade destrutivo automático.

Este checklist não autoriza commit, release, migration de produção ou deploy.
