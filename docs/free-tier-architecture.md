# Arquitetura gratuita e dependências externas

**Decisão de produto registrada:** o Investment Dashboard deve ter funcionamento sem despesa obrigatória. Este documento não afirma que um plano gratuito específico estará disponível ou que um painel está configurado.

## Regras de custo

- Não ativar cobrança automática, plano pago, API premium ou serviço comercial sem decisão explícita.
- Priorizar hospedagem/banco/Auth gratuitos quando os limites e termos forem adequados.
- Preferir bibliotecas open source e operações manuais/CSV.
- Uma função que exceda uma quota deve parar com estado claro, limitar consulta ou oferecer processo manual; não contornar quota por scraping.
- O produto essencial deve continuar acessível ou local mesmo que a integração opcional fique desabilitada.
- Não há intenção de assinatura ou monetização.

## Componentes e estratégia

| Camada | Preferência | Fallback sem custo obrigatório |
|---|---|---|
| Frontend | Hospedagem estática gratuita, build público/demo separado do privado. | Executar localmente e manter demo offline. |
| API | Hospedagem gratuita enquanto suporta HTTPS, deploy manual e ambiente seguro. | Reduzir recursos remotos, operar localmente; não abrir a base financeira. |
| PostgreSQL | Tier gratuito com backup/limites confirmados, papel runtime restrito e RLS. | PostgreSQL local/backups do proprietário. Não depender de tier volátil como único backup. |
| Auth | Supabase Auth gratuito enquanto os limites e termos servirem. | Acesso privado local autorizado; não retirar autenticação de produção. |
| Dados de mercado | Somente fonte gratuita, permitida, licenciável e com dados válidos. | Flag false, estado unavailable, cotação manual com origem/data se houver fluxo aprovado. |
| Renda fixa | BCB/SGS público existente e cache/backoff, respeitando qualidade e calendário. | Estimar null/indisponível quando taxas não estiverem completas; registro manual. |
| Importação | CSV local processado no navegador/API privada sem enviar a terceiros. | Digitação manual revisável. |
| Dependências | Pacotes open source e lockfiles versionados. | Remover/disable optional feature se manutenção/risco superar benefício. |

Os itens acima são preferências arquiteturais, não confirmação de preço atual, plano contratado ou configuração em Render/Vercel/Supabase. Limites e termos são variáveis no tempo e precisam de conferência em fonte oficial antes de habilitar.

## Cache, limites e resiliência

- Cachear apenas conteúdo público por ativo/período, com TTL visível; nunca compartilhar resposta de carteira entre usuários.
- Deduplicar requisições, respeitar Retry-After, aplicar timeout e budget de requests.
- Guardar tokens somente no backend; nenhuma chave financeira em variável VITE_*.
- Evitar polling constante; preferir carga sob demanda e janela de consulta limitada.
- Colocar flags opt-in false; remover chamada upstream quando desabilitada.
- Não persistir preço/valor sem origem, data, moeda, base e status.
- Exibir disabled, rate_limited, stale, partial e unavailable sem fallback fabricado.
- Isolar consumo e limite por usuário antes de permitir convidados.

## Riscos de planos gratuitos

- Limite de requisição, armazenamento, usuários, conexões e execução pode ser alterado.
- Projetos podem ser suspensos por inatividade ou exceder quota.
- Backups podem não existir no tier, ter retenção limitada ou exigir ação manual.
- DNS, logs, builds e egress podem ter cotas.
- API gratuita pode bloquear, mudar cobertura, licença ou schema.
- Cache em memória por worker não é distribuído e reinício pode limpá-lo.
- Um tier grátis não elimina o risco de indisponibilidade ou perda de dados.

Antes de release, registrar plano e política conferidos, limites medidos, comportamento após quota, backup independente e procedimento de exportar/restaurar. Não assumir continuidade perpétua; ter fallback local e dados essenciais exportáveis.

## Alternativas condicionais preservadas

APIs pagas, Open Finance, agregadores, ferramentas comerciais e infraestrutura premium podem ser revisitados como alternativas opcionais. Continuam fora do requisito base e não entram no orçamento até aprovação expressa. Comparar custo, licença, dados, segurança e possibilidade de cancelamento; nunca acoplar a função financeira essencial de modo que a falta do serviço invente informação.

## Aceite de funcionalidade externa

- modo desabilitado usa zero chamadas externas;
- falha/limite não bloqueia registro local de operações;
- credenciais não são expostas;
- fonte e atualização aparecem na UI;
- quotas/cache/backoff possuem testes;
- verificar termos/licença e limites antes da ativação;
- o usuário pode continuar usando ledger, demo e exportação sem serviço pago.
