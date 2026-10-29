# Changelog

## v3.0.4 — notas preparadas em 29/10/2026

> Notas para a release oficial. Nenhuma tag, GitHub Release, deploy ou migration foi criada
> nesta auditoria. O responsável reporta o deployment; o SHA implantado ainda requer
> conferência no painel Vercel.

### Adicionado

- Histórico privado e cronológico de operações de ações e CDB em `/historico`, com filtros
  por período, classe e ativo.
- Série unificada baseada em movimentos efetivos, respeitando revisões `REPLACE` e `VOID` e
  o isolamento por proprietário.
- Indicadores de compras/aplicações, vendas líquidas/resgates de principal, fluxo líquido,
  capital aplicado em posições abertas e composição por classes.
- Gráficos de fluxos com filtros temporais, tooltips monetários e layout responsivo.

### Regras e limites

- Vendas líquidas e resgates de principal são fluxos de saída; não são tratados integralmente
  como lucro/rendimento. Fluxo líquido não é patrimônio nem retorno da carteira.
- Posições manuais de CDB sem base confiável permanecem fora dos agregados de composição.
- Valores de mercado derivados de cotações externas são estimativas e devem ser conferidos
  na corretora.
- Histórico de preços de ações da 3.0.3 permanece preservado e desabilitado por padrão por
  `EQUITY_HISTORY_ENABLED=false`; cotações pontuais usam o controle independente de mercado.
- Nenhuma migration é necessária para a 3.0.4.

### Validação reportada nesta auditoria

- Backend focalizado: 232 aprovados.
- Frontend: 149 aprovados em 14 arquivos de teste.
- Build de produção: concluído; o Vite reporta chunk principal acima de 500 kB.
