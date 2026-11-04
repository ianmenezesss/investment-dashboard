# Diagnóstico dos 503 administrativos no Render — 04/11/2026

## Conclusão com a evidência disponível

O sucesso do login `investment_access_operator` no Docker, com `session_user` correto e membership administrativa, demonstra que aquele caminho de conexão funciona. Não comprova o valor efetivamente carregado no Render, a interpretação de uma URI com senha codificada, a CA disponível no filesystem Linux, a validação de hostname, DNS/rede, capacidade do pooler ou o estado dos workers em execução.

Não há evidência suficiente para atribuir o erro a uma senha, certificado ou permissão específica. A investigação local abaixo não conectou ao banco remoto nem alterou o banco.

## O que o código comprova

| Arquivo | Comportamento relevante |
| --- | --- |
| `backend/app/database.py` | `Settings()` é criado na importação; variáveis do processo têm precedência sobre o dotenv relativo `../.env`. O valor não é recarregado a cada requisição. A engine administrativa e sua session factory também são criadas uma vez por processo. |
| Mesmo arquivo | Se ADMIN_DATABASE_URL estiver preenchida, valida driver `postgresql+psycopg`, login distinto, mesmo host/porta/banco do runtime e, em produção, `sslmode=verify-full`. Não testa senha, DNS, CA, TLS ou login durante essa validação. |
| Mesmo arquivo | Engines são lazy: `create_engine` e `Session()` não comprovam conexão. `pool_pre_ping` verifica uma conexão no checkout, sem antecipar isso na inicialização. `hide_parameters=True` não é um sanitizador geral de mensagens libpq. |
| Mesmo arquivo | Ausência da URL administrativa gera HTTP 503 explícito em `get_admin_db`; não gera, por si só, o log SQLAlchemy `database_request_failed`. URL inválida para os validators tende a impedir a importação/startup, em vez de falhar apenas nos endpoints. URI sintaticamente válida com credencial/CA errada passa pelo startup. |
| `backend/app/main.py` | `/health` executa SELECT 1 e verifica a role usando DATABASE_URL, nunca ADMIN_DATABASE_URL. O lifespan não abre/testa a conexão administrativa. Um health 200 é compatível com administração inacessível. |
| `backend/app/accounts.py` | As três listagens passam por autenticação, `get_admin_db` e `_admin_context`. A primeira consulta administrativa é `set_config` local à transação; o checkout pode falhar antes de qualquer comando chegar ao banco. Depois é validado o contexto protegido e só então a listagem. |
| `backend/app/main.py` | `connection_or_operational` é fallback para OperationalError cujo SQLSTATE não foi classificado. Pode faltar SQLSTATE ou existir outro código, por exemplo de recursos/indisponibilidade/cancelamento. Não comprova sozinho erro TCP. SQLSTATE 42501 seria `permission`; 42883 seria `sql`. Contexto administrativo recusado gera HTTPException 503 com outra mensagem, sem esse log SQLAlchemy. |
| `backend/scripts/check_access_configuration.py` | A sonda anterior lê dotenv, não o ambiente efetivo completo, testa DATABASE_URL e omite a distinção de falhas. Portanto não resolve este diagnóstico administrativo no Render. |
| `render.yaml` e `backend/.env.production.example` | São modelos, não prova da configuração implantada. Apontam `PGSSLROOTCERT` para um Secret File Linux. Não comprovam que o arquivo exista, seja legível ou corresponda à CA efetivamente usada pela URL administrativa. |

Os logs informados favorecem investigar o checkout/driver comum aos três endpoints antes de alterar grants ou RLS. Como `authenticate` consulta o runtime e converte suas falhas em HTTPException, o log SQLAlchemy das listagens reforça a hipótese da conexão administrativa; a etapa exata ainda exige observação no Render.

## Hipóteses que exigem teste no Render

1. **CA divergente entre as URLs.** `sslrootcert` explícito na URL administrativa prevalece sobre `PGSSLROOTCERT`. Um caminho Windows copiado para Linux, arquivo ausente/inacessível, PEM inválido, CA inadequada ou hostname errado pode produzir OperationalError no primeiro checkout. Não retirar `verify-full`. A CA comum ausente deveria afetar também uma conexão runtime nova se os parâmetros forem iguais; um health usando conexão já aberta pode continuar 200.
2. **URI diferente da credencial testada.** Senha transmitida como parâmetro separado no Docker não prova que seus caracteres reservados estejam codificados corretamente na URI do Render. Verificar também aspas literais, espaços externos, usuário completo do pooler, sufixo do projeto, porta e parâmetros. Não imprimir o valor ou reconstruí-lo em argumentos de shell.
3. **Workers/configuração antigos.** O Shell pode ter uma configuração diferente do processo que está atendendo. Confirmar commit implantado, início do processo e aplicação das alterações de ambiente no painel. O comando Restart Service do Render usa os valores do deploy existente; não presumir que ele publique alterações apenas salvas para outro deploy.
4. **DNS/rede/capacidade.** Session Pooler na porta 5432 é a alternativa IPv4 documentada. Um host direto, timeout, resolução diferente, regras de rede ou limite de clientes/backends pode falhar no Render apesar de funcionar no Docker. O código valida igualdade entre endpoints, mas não exige um host de Session Pooler.
5. **Pool/processos.** Há duas engines independentes. Sem parâmetros explícitos, os defaults de QueuePool são 5 conexões + 10 de overflow por engine, por processo. São tetos sob carga, não conexões pré-abertas. Capacidade do pooler por usuário/projeto pode ser menor. QueuePool TimeoutError costuma ter outra exception_category; o pooler recusando conexões pode aparecer como OperationalError. Não aumentar pools para tentar resolver uma recusa de capacidade.
6. **Conexão abre, mas SQL falha.** Membership do login não garante que o UUID administrativo esteja no registro protegido nem que todos os objetos e grants estejam corretos. Investigar isso depois de comprovar a conexão. Não executar migrations ou conceder privilégios para testar uma hipótese de rede/TLS.

## Sonda segura preparada

`backend/scripts/diagnose_admin_connection.py` usa os Settings e as engines reais do projeto, sem modificar o código da aplicação. O modo padrão só inspeciona configuração e legibilidade/parse do certificado; não abre conexão. O modo explícito executa SELECTs de metadados sob transação read-only, com statement_timeout local de cinco segundos. `set_config` só existe na transação revertida, sem alterar tabelas ou permissões. Não chama Supabase Auth nem lê registros financeiros/listagens de usuários.

Saída: somente indicadores, etapas, SQLSTATE validado e categorias fixas. Não imprime URL, host, nome de usuário real, senha, token, caminho de certificado, corpo da exceção ou traceback. Um resultado `ok` da sonda é sucesso da etapa técnica; verificar separadamente `admin_context_authorized` e `unsafe_login`.

No Shell do **serviço e deploy que apresentam o erro**, a partir do diretório que contém `app/database.py`:

```bash
python scripts/diagnose_admin_connection.py
python scripts/diagnose_admin_connection.py --connect-read-only
```

Como estes arquivos são locais e não foram publicados, o caminho acima só existirá após disponibilizar o arquivo. Para testar sem commit/push/deploy, copiar apenas a sonda revisada para `/tmp/diagnose_admin_connection.py` pelo Shell/Editor do Render e executar no diretório backend:

```bash
python /tmp/diagnose_admin_connection.py
python /tmp/diagnose_admin_connection.py --connect-read-only
```

Não usar `printenv`, `env`, `echo "$ADMIN_DATABASE_URL"`, `set -x`, SQLAlchemy echo ou `print(exc)`. Não fornecer DSNs/senhas em argumentos. As credenciais são lidas das configurações já disponíveis no serviço. A sonda não faz retry nem altera pools/TLS. O timeout de conexão é o mesmo configurado pela aplicação; resolução DNS/múltiplos endereços pode fazer o tempo total superar cinco segundos.

Interpretação:

| Resultado | Próxima verificação |
| --- | --- |
| `settings_or_engine_initialization` | Divergência do modelo/configuração/driver do deploy. Investigar com mensagens fixas por campo, sem imprimir ValidationError bruto ou DSN. |
| `admin_configuration_missing` | Variável/factory ausente no processo da sonda. Conferir serviço, deploy e ambiente efetivo. |
| Runtime abre, admin falha em `connect` | Comparar parâmetros por indicadores: origem da CA, arquivo, TLS, credencial codificada, capacidade do usuário/pooler. |
| `tls_ca_file` / `tls_verification` | Secret File Linux, precedência da query, CA oficial do projeto e hostname original. PEM parseável não comprova confiança na cadeia do servidor. |
| `authentication` | Credencial exata do serviço e codificação da URI; não redefinir senha por tentativa. |
| `dns`, `network_route`, `timeout`, `connection_capacity` | Logs do pooler e observações de rede do próprio Render no mesmo horário. |
| Conexão abre, `admin_context` falha | SQLSTATE/objeto/função/grant. Se authorized=false ou unsafe=true, revisar metadados administrativos de forma somente leitura. |
| Ambas abrem/contexto correto, endpoints continuam 503 | Processo antigo, divergência entre workers, carga ou falha intermitente. Correlacionar request_id, horário, deploy e etapa da requisição real. |

Se necessário, instrumentar depois `database_error` com SQLSTATE validado, engine/etapa fixa e categorias allowlist semelhantes à sonda. O handler atual preserva sigilo, mas omite informação necessária para concluir a causa. Não registrar mensagens livres do driver, `.params`, objetos Settings, URL de engine ou traceback. Nenhuma instrumentação da aplicação foi aplicada nesta investigação.

Validação local: três testes com erros/URLs sintéticos aprovados, incluindo não exposição de credenciais e precedência da CA. Nenhuma conexão de produção foi tentada. Arquivos locais novos: sonda, `backend/tests/test_admin_connection_diagnostic.py` e este documento. Sem commit/push/migration ou alteração do banco.

Fontes oficiais: [TLS e CA PostgreSQL](https://www.postgresql.org/docs/current/libpq-ssl.html), [conexões Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [Secret Files Render](https://render.com/docs/configure-environment-variables), [semântica de Restart Service](https://render.com/docs/deploys).
