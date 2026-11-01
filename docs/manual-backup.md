# Backup manual único — Supabase Free / Investment Dashboard

**Estado:** um único arquivo foi gerado pelo proprietário em armazenamento local protegido fora do checkout. Em 30/10/2026, a revisão local encontrou 101085 bytes e SHA-256 coincidente com o valor registrado pelo proprietário. Não guarde aqui o hash, a frase, a URL PostgreSQL ou dados do dump. O banco de produção não foi acessado novamente nesta revisão. O restore deste arquivo real não foi executado; depende de autorização específica para inserir a frase de proteção localmente.

## Estratégia e compatibilidade

O plano permanece **manual**, sem agendamento, workflow GitHub Actions, retenção automática ou serviço pago. O procedimento original para schema 009 permanece documentado para compatibilidade histórica; a candidata v2.0 acrescenta o formato `IDBKP010`, que exige a tabela de observações patrimoniais e Alembic `010`. O leitor de restauração aceita os formatos 009 e 010 e valida as tabelas exigidas pelo cabeçalho. Nenhum script aplica migrations ou escreve no banco de origem. Consulte [backups Supabase](https://supabase.com/docs/guides/platform/backups) e [métodos de conexão PostgreSQL](https://supabase.com/docs/guides/database/connecting-to-postgres).

O resultado é um arquivo `.idbackup`: dump custom PostgreSQL cifrado em streaming com AES-256-GCM, marcado `IDBKP009` ou `IDBKP010`. A frase de proteção é digitada sem eco, nunca passada em argumentos ou gravada em log. O processo pede confirmação literal antes de conectar, não sobrescreve destino existente, não grava dump em claro no host e valida a autenticação, descompressão e revisão correspondente antes de promover o arquivo. O SHA-256 impresso identifica o arquivo cifrado; AES-GCM também detecta alteração ou frase incorreta.

`pg_dump` e `pg_restore` são ferramentas PostgreSQL usuais no plano Free; a disponibilidade depende de o projeto aceitar a conexão Session Pooler e de o usuário ter `SELECT` suficiente. Limites de rede, conexões ou privilégios podem impedir o dump. O preflight exige banco PostgreSQL 17, TLS e a revisão única correspondente ao script escolhido: `009` no fluxo legado ou `010` no fluxo da v2.0. Não se deve contornar uma falha de permissão ampliando o papel runtime: use uma credencial de backup aprovada, somente com os privilégios necessários.

## Preparação local e backup real

O registro anterior informa que o proprietário gerou um arquivo de backup em armazenamento local protegido, identificado como esquema 009. Esse artefato não foi aberto nesta implementação. Não gere uma segunda cópia nem execute um script de produção sem autorização específica. Nunca cole URL, senha, frase de proteção ou CA no Git, issue, chat ou log.

O procedimento abaixo documenta o fluxo futuro; não foi executado nesta implementação. Uma geração de backup real requer autorização própria e a URL/CA não são necessárias para os testes locais sintéticos.

Para a candidata v2.0, o script versionado é `backend/scripts/backup_supabase_010.py`. O comando não foi executado durante a implementação; exige autorização própria e credenciais locais.

```powershell
python backend/scripts/backup_supabase_010.py --output '<PASTA_PROTEGIDA_FORA_DO_REPOSITORIO>\investment-dashboard-v2.0.0.idbackup'
```

O script 010 solicita a frase duas vezes e exige `BACKUP PRODUCTION 010`. O script legado `backup_supabase_009.py` continua disponível para schema 009 e exige a confirmação 009. Em sucesso, não é criado arquivo de manifesto ou log. Limpe variáveis de sessão após uso e guarde a frase separadamente em meio protegido. A candidata v2.0 não declara backup 010 de produção nem aplicação de migration.

## Ensaio e verificação do restore

O ensaio automatizado da candidata usa fixtures fictícias, PostgreSQL 17 efêmero e formato 010. A integração executa migrations 001–010, grava registros sintéticos, tira dump, cifra, autentica/descriptografa, restaura em outro PostgreSQL descartável e compara contagens, RLS/FORCE RLS, policies, triggers, grants e isolamento de proprietários. O leitor também mantém compatibilidade 009. Os containers não recebem dados de produção; a frase sintética não é reutilizável. O backup real histórico mencionado no registro acima não foi restaurado nem revalidado nesta implementação.

Para restaurar um arquivo real futuramente **somente em PostgreSQL descartável**:

```powershell
python backend/tests/restore_supabase_backup.py `
  --backup '<PASTA_PROTEGIDA_FORA_DO_REPOSITORIO>\investment-dashboard-v1.0.0.idbackup' `
  --sha256 '<SHA256 impresso pelo backup>'
```

O restaurador solicita a frase e confirmação `DESCARTAVEL`. Ele valida o hash opcional e a tag AES-GCM antes de usar o conteúdo; a cópia em claro fica apenas em `tmpfs` do container isolado, sem rede e é removida quando o container termina. O restaurador não aceita destino Supabase nem URL de banco. Não use `pg_restore` diretamente no Supabase ativo.

## Escopo recuperável e limites

O artefato contém o schema PostgreSQL `public`: tabelas, sequências, índices, constraints, funções/triggers/policies incluídos pelo `pg_dump`, grants de objetos disponíveis à credencial e os dados acessíveis das tabelas da aplicação. No formato 010 isso inclui `portfolio_valuation_observations` e `alembic_version=010`; o formato 009 contém o conjunto anterior e `alembic_version=009`. As ACLs exigem que os papéis referenciados existam no destino; o dump não cria roles globais nem repõe senhas/atributos de cluster. O restore de ensaio recria roles locais fictícias e verifica grants e RLS.

Não é uma imagem completa do projeto Supabase e não recupera:

- contas/credenciais/sessões do Supabase Auth ou a configuração do serviço Auth;
- arquivos binários do Supabase Storage nem políticas/configurações externas do projeto;
- variáveis secretas, domains, CORS, CSP, configurações de Render/Vercel, chaves JWT ou integração de preços;
- metas financeiras guardadas apenas no `localStorage` de cada navegador;
- schemas gerenciados fora de `public`, roles globais e alterações feitas após o instante do dump.

Usuários UUID referenciados pelos registros públicos permanecem nos dados da aplicação, mas isso não restaura suas contas Auth. Em uma recuperação futura, primeiro recrie/configure serviços e papéis em ambiente separado, confirme compatibilidade e faça reconciliação de gravações posteriores ao backup. Não restaure sobre produção como teste e não trate este único ponto como estratégia de alta disponibilidade.

## Arquivos e proteção do repositório

`*.idbackup` e arquivos `.partial` são ignorados pelo Git. O script também recusa caminho de saída ou arquivo de restore dentro do checkout. Ainda assim, antes de qualquer commit, confira `git status` e os arquivos staged; `.gitignore` não remove um arquivo que já esteja rastreado.
