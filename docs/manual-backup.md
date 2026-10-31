# Backup manual único — Supabase Free / Investment Dashboard v1.0.0

**Estado:** um único arquivo foi gerado pelo proprietário em armazenamento local protegido fora do checkout. Em 30/10/2026, a revisão local encontrou 101085 bytes e SHA-256 coincidente com o valor registrado pelo proprietário. Não guarde aqui o hash, a frase, a URL PostgreSQL ou dados do dump. O banco de produção não foi acessado novamente nesta revisão. O restore deste arquivo real não foi executado; depende de autorização específica para inserir a frase de proteção localmente.

## Estratégia e compatibilidade

O plano escolhido é fazer **um único backup manual** antes da release v1.0. Não existe agendamento, workflow GitHub Actions, política de retenção de cópias ou serviço pago. O plano Free do Supabase não oferece backups automáticos gerenciados; a própria documentação recomenda exportação manual por Supabase CLI e off-site backup. Este projeto usa `pg_dump`, também suportado pelo PostgreSQL. O Supabase recomenda conexão direta para operações de dump/restore; se a rede IPv4 não alcançar o endpoint direto (IPv6), o shared Session Pooler da porta `5432` é a alternativa disponível em todos os planos. Não use transaction pooler `6543`. A conexão deve usar TLS com `sslmode=verify-full` e a CA oficial do Supabase. O usuário do banco precisa ter acesso de leitura a todos os dados e objetos públicos exportados. O script recusa qualquer Alembic diferente de `009` e não executa migrations nem escreve no banco. Consulte [backups Supabase](https://supabase.com/docs/guides/platform/backups) e [métodos de conexão PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres).

O resultado é um único arquivo `.idbackup`: dump custom PostgreSQL (com compressão do formato custom) cifrado em streaming com AES-256-GCM. A frase de proteção é digitada sem eco, nunca passada em argumentos ou gravada em log. O script pede confirmação literal antes de conectar, não sobrescreve destino existente, não grava dump sem cifrar no host e valida a autenticação, a descompressão completa e a revisão `009` antes de promover o arquivo. O SHA-256 impresso identifica o arquivo cifrado; AES-GCM também detecta alteração ou frase incorreta.

`pg_dump` e `pg_restore` são ferramentas PostgreSQL usuais no plano Free; a disponibilidade depende de o projeto aceitar a conexão Session Pooler e de o usuário ter `SELECT` suficiente. Limites de rede, conexões ou privilégios podem impedir o dump. O preflight falha sem produzir backup se não confirmar banco PostgreSQL 17, revisão única `009` e TLS. Não se deve contornar uma falha de permissão ampliando o papel runtime: use uma credencial de backup aprovada, somente com os privilégios necessários.

## Preparação local e backup real

Os testes sintéticos em PostgreSQL descartável foram aprovados (ver abaixo). O backup único já foi gerado após autorização; **não gere uma segunda cópia nem execute novamente o script de produção**. Nunca cole a URL, senha, frase de proteção ou CA no Git, issue, chat ou log.

O procedimento abaixo é a referência para recuperação documentada futura, não uma instrução para gerar outro arquivo. Quando uma futura substituição for necessária, confirme primeiro uma nova autorização. Para o artefato atual, a URL/CA não são necessárias para validar o hash local.

```powershell
python backend/scripts/backup_supabase_009.py --output '<PASTA_PROTEGIDA_FORA_DO_REPOSITORIO>\investment-dashboard-v1.0.0.idbackup'
```

No uso futuro, o script solicita a frase duas vezes e, antes da primeira consulta, exige `BACKUP PRODUCTION 009`. Em sucesso, não é criado arquivo de manifesto ou log. Limpe as variáveis da sessão depois do uso. A frase do arquivo atual deve permanecer guardada separadamente em meio protegido. Como existe só uma cópia, perda do arquivo ou da frase elimina este ponto de recuperação.

## Ensaio e verificação do restore

O ensaio automatizado usa fixtures fictícias, PostgreSQL 17 efêmero e o mesmo formato cifrado. A integração executa migrations 001–009, grava operações/eventos sintéticos, tira dump, cifra, autentica/descriptografa, restaura em outro PostgreSQL descartável e compara contagens, fingerprints de linhas, RLS/FORCE RLS, policies, triggers, role runtime, grants e visibilidade de dois proprietários. Os containers não recebem dados de produção. A frase sintética do teste não é reutilizável. O backup real atual teve seu tamanho e hash conferidos, mas sua descriptografia/restauração ainda não foi testada; somente prosseguir quando houver autorização específica para inserir a frase localmente.

Para restaurar um arquivo real futuramente **somente em PostgreSQL descartável**:

```powershell
python backend/tests/restore_supabase_backup.py `
  --backup '<PASTA_PROTEGIDA_FORA_DO_REPOSITORIO>\investment-dashboard-v1.0.0.idbackup' `
  --sha256 '<SHA256 impresso pelo backup>'
```

O restaurador solicita a frase e confirmação `DESCARTAVEL`. Ele valida o hash opcional e a tag AES-GCM antes de usar o conteúdo; a cópia em claro fica apenas em `tmpfs` do container isolado, sem rede e é removida quando o container termina. O restaurador não aceita destino Supabase nem URL de banco. Não use `pg_restore` diretamente no Supabase ativo.

## Escopo recuperável e limites

O artefato contém o schema PostgreSQL `public`: tabelas, sequências, índices, constraints, funções/triggers/policies incluídos pelo `pg_dump`, grants de objetos disponíveis à credencial e os dados acessíveis das tabelas da aplicação, incluindo operações, renda fixa, `financial_events`, `financial_event_revisions` e `alembic_version=009`. As ACLs exigem que os papéis referenciados existam no destino; o dump PostgreSQL não cria roles globais nem repõe senhas/atributos de cluster. O restore de ensaio recria roles locais fictícias e verifica grants e RLS.

Não é uma imagem completa do projeto Supabase e não recupera:

- contas/credenciais/sessões do Supabase Auth ou a configuração do serviço Auth;
- arquivos binários do Supabase Storage nem políticas/configurações externas do projeto;
- variáveis secretas, domains, CORS, CSP, configurações de Render/Vercel, chaves JWT ou integração de preços;
- metas financeiras guardadas apenas no `localStorage` de cada navegador;
- schemas gerenciados fora de `public`, roles globais e alterações feitas após o instante do dump.

Usuários UUID referenciados pelos registros públicos permanecem nos dados da aplicação, mas isso não restaura suas contas Auth. Em uma recuperação futura, primeiro recrie/configure serviços e papéis em ambiente separado, confirme compatibilidade e faça reconciliação de gravações posteriores ao backup. Não restaure sobre produção como teste e não trate este único ponto como estratégia de alta disponibilidade.

## Arquivos e proteção do repositório

`*.idbackup` e arquivos `.partial` são ignorados pelo Git. O script também recusa caminho de saída ou arquivo de restore dentro do checkout. Ainda assim, antes de qualquer commit, confira `git status` e os arquivos staged; `.gitignore` não remove um arquivo que já esteja rastreado.
