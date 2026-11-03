# Limites da Íris e do envio de convites

## Origem do limite de duas operações

O limite localizado era de **dois pedidos de envio de e-mail por hora**, em `backend/app/accounts.py`, adicionado como proteção conservadora para o SMTP padrão do Supabase. Não era um limite de duas consultas à Íris. A Íris tinha cinco mensagens por minuto e cinquenta por dia no PostgreSQL; o fallback local só limitava por minuto.

A documentação oficial consultada em 03/11/2026 informa que o [SMTP padrão do Supabase](https://supabase.com/docs/guides/auth/auth-smtp) envia apenas para endereços da equipe do projeto e tem limite de duas mensagens por hora. Convites para usuários externos exigem configuração SMTP apropriada; aumentar um número no código não altera essa restrição. Conferir também [Auth Rate Limits](https://supabase.com/docs/guides/auth/rate-limits). Não houve alteração do projeto remoto ou contratação de serviço.

## Configuração da Íris

| Variável | Padrão | Aplicação |
| --- | --- | --- |
| `ASSISTANT_ADMIN_PER_MINUTE` | 10 | Administradores em `INVITATION_ADMIN_IDS` e modo local |
| `ASSISTANT_ADMIN_PER_DAY` | 500 | Administradores e modo local |
| `ASSISTANT_USER_PER_MINUTE` | 5 | Demais contas privadas ativas |
| `ASSISTANT_USER_PER_DAY` | 100 | Demais contas privadas ativas |
| `ASSISTANT_COOLDOWN_SECONDS` | 2 | Intervalo mínimo por usuário |

Os números são tetos internos configuráveis, não capacidade garantida do provedor. O servidor usa a identidade da sessão validada para escolher a regra; o cliente não pode pedir uma cota administrativa. A demonstração permanece offline, com zero chamadas à Groq. Não foi criado um endpoint público de IA.

Na produção, a migration 018 mantém contadores, cooldown e uma reserva de execução no PostgreSQL. Duas instâncias disputando o mesmo usuário não podem iniciar chamadas simultâneas. O lease expira em 30 segundos se o processo cair; uma resposta atrasada não libera a reserva de uma chamada mais nova. Respostas e falhas liberam a reserva; tentativas iniciadas continuam consumindo cota, pois podem consumir recursos externos. A reserva também rejeita membership revogada ou com trial expirado.

A cota diária renova à meia-noite UTC, e a janela de minuto começa na primeira mensagem. O fallback de desenvolvimento/testes oferece as mesmas regras em memória e reinicia com o processo. Respostas de limite incluem `Retry-After`; cota interna retorna 429, enquanto indisponibilidade ou limite da Groq retorna 503 com mensagem distinta. Não há repetição automática da chamada ao provedor.

Os [limites da Groq](https://console.groq.com/docs/rate-limits) valem por organização, considerando requisições e tokens. O limite efetivo pode ser inferior aos tetos por usuário, especialmente porque cada pergunta inclui o contexto educativo estático. Conferir o painel Limits da organização antes de elevar cotas; o backend respeita 429 e o `Retry-After` do provedor. Nenhuma troca de conta, chave ou modelo é usada para contornar quotas. Cada resposta continua limitada a 350 tokens de conclusão.

Validação local: a partir de `backend`, executar `.venv/Scripts/python.exe -m pytest tests/test_assistant.py`. O ensaio PostgreSQL descartável inclui `tests/assistant_quota_postgres.py`. A entrega principal registra os resultados e eventuais limitações do ambiente.
