# Investment Dashboard 2.0 — expansão restrita por convite

**Status:** proposta futura; não faz parte das releases v4/v5 por padrão e não autoriza cadastro, convites ou mudanças remotas.

## Decisão de produto

Investment Dashboard 2.0 é nome provisório da expansão multiusuário, não a Fase técnica 2.x de renda fixa. O público futuro é pequeno e selecionado. Acesso somente por convite ou aprovação explícita; sem registro público irrestrito e sem monetização planejada. O projeto precisa funcionar sem despesas obrigatórias.

A ideia anterior no roadmap menciona solicitação de acesso, aprovação manual e convite individual com expiração. O detalhe de preço/planos não foi localizado e não está aprovado. [Roadmap](roadmap.md)

## Fronteiras de dados e experiência

1. **Demo pública:** fixtures fictícias e offline, sem API privada, Supabase Auth ou banco financeiro.
2. **Carteira do proprietário:** identidade privada existente; convidados nunca recebem seus registros.
3. **Convidado:** identidade individual, carteira vazia/isolada e seus próprios registros. Não recebe cópia de dados do proprietário.
4. **Recrutador:** pode explorar demo pública ou uma conta de demonstração isolada com dados próprios. Convite não significa permissão para ver investimentos do proprietário.
5. **Admin:** pode gerir metadados de acesso/invites; sem acesso automático ao conteúdo financeiro. Qualquer fluxo excepcional de suporte teria que ser uma decisão separada, mínimo, consentido, temporário e auditado.

## O que já está preparado

- Supabase Auth individual, validação JWT/JWKS no backend e allowlist de UUIDs.
- owner_id em modelos, filtros no servidor e contexto transacional para políticas RLS.
- Papel PostgreSQL de runtime separado de DDL e sem BYPASSRLS conforme migrations/configuração.
- Testes de autenticação, autorização e isolamento por proprietário.
- Build demo separado e repositórios demo/privado com fronteira de rede.

Isso é uma base de isolamento técnico, não a plataforma de onboarding. O acesso atual restrito por allowlist não é sistema de convites e não deve ser convertido em cadastro aberto.

## Escopo mínimo de um MVP futuro

- Criar convite individual com token de uso único, validade, revogação e limite de tentativas; token armazenado como hash e nunca em logs.
- Aprovação manual e provisionamento pelo Supabase Auth; configuração de signup público continua desligada.
- Fluxo de aceite, senha/recuperação de conta, expiração e remoção de acesso.
- Ferramenta administrativa com metadados mínimos, trilha de auditoria, ações segregadas e sem leitura de operações.
- Owner_id obrigatório e RLS nas tabelas financeiras; toda query/export usa proprietário autenticado do servidor.
- Testar acesso cruzado a endpoint, ID, cache, download, consultas em páginas, restore e relatórios com pelo menos duas identidades.
- Limites locais por conta para requests caros; quotas conservadoras nos provedores gratuitos; cache apenas para dados públicos, nunca respostas de carteira.
- Aviso de privacidade, finalidade, retenção, canal de suporte, processo de exportação/eliminação e resposta a incidente. Revisão de LGPD aplicável antes de convidar terceiros.
- Backup/restore, monitoramento operacional sem conteúdo financeiro e plano de suspensão/abuso.

## Segurança e operação

- Nunca confiar apenas no filtro frontend; autorização é backend e RLS.
- Admin não pode consultar carteiras por padrão. Suporte não recebe service role no navegador nem acesso direto ao PostgreSQL.
- Rotacionar/revogar acesso via processo auditável; logout local não revoga instantaneamente JWT já emitido.
- Rever MFA, abuso, rate limit distribuído, retenção, restore e logs antes da exposição.
- Convites e notificações não devem conter dados financeiros.
- Não migrar registros locais com owner nulo automaticamente para o proprietário nem para convidados.
- Conta de recrutador não recebe carteira real; a demo continua opção prioritária.

## Custos e limite do compromisso

Sem intenção de assinatura ou venda de planos. Projetar para os níveis gratuitos existentes, mas reconfirmar preço, limite, inatividade, retenção e política antes de cada publicação. Se os limites mudarem, reduzir/limitar recurso, retornar indisponibilidade ou manter operação manual. Não ativar gasto automático.

Uma expansão com custo obrigatório, API paga ou Open Finance pago exigiria nova decisão explícita. Não há limite de usuários nem estimativa financeira aprovada; o MVP deve definir um teto pequeno e testar quotas antes de convidar grupo maior.

## Dependências e migrations

Prováveis entidades novas: convite/revogação e auditoria administrativa. Podem usar Auth e armazenamento existente ou exigir tabela/Edge Function; escolher após threat model. Qualquer migration precisa de teste em banco descartável, política RLS, role/grants mínimos, backup e aprovação explícita.

Não habilitar contas antes de:
- testes de dois proprietários sob runtime restrito no PostgreSQL;
- confirmação de signup desabilitado e allowlist/provisionamento;
- revisão de suporte e privacidade;
- limites e procedimento de custo zero;
- restauração ensaiada, observabilidade e incident response.

## Aceite do MVP

- signup público negado;
- convite individual expira, é uso único e revogável;
- convidados entram somente na própria carteira;
- proprietário e convidados não enxergam uns aos outros;
- administrador não lê carteiras;
- demo permanece offline;
- logs/cache/exportação não vazam dados;
- custos obrigatórios zero, consumo controlado e fallback documentado;
- onboarding, privacidade, recuperação de conta, suporte, backup e remoção validados.

Essa proposta não declara a plataforma pronta e mantém expansão como projeto posterior à estabilidade pessoal.
