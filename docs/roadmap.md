# Roadmap do Investment Dashboard

Registro atualizado na Fase **2.0.2**, em 28/10/2026. As funcionalidades da Fase 3
continuam planejadas e não foram implementadas nesta entrega.

## Fase 2 — renda fixa

- **2.0.1:** contratos CDB, lotes e movimentações imutáveis de principal, validados em
  PostgreSQL descartável; sem rendimentos ou impostos.
- **2.0.2 (implementada para revisão):** consulta histórica privada de CDI diário (SGS 12)
  e Selic diária (SGS 11), com Decimal, cache e controle de chamadas. Sem migration,
  cálculo de rendimento ou UI. Ver [contrato e limites](phase-2.0.2-bcb-rates.md).
- Cálculos de rendimentos/tributação e UI de renda fixa não fazem parte desta fase;
  escopo e versão de entregas futuras ainda devem ser definidos.

## Fase 3 — exploração de ativos e histórico

| Subfase planejada | Escopo |
| --- | --- |
| 3.0.1 | Página individual de cada ativo, com posição, operações e indicadores disponíveis, preservando isolamento por usuário e identificação das referências |
| 3.0.2 | Resumo mensal e anual por ativo e carteira, separando movimentações de capital, resultado realizado e resultados que os dados permitirem calcular |
| 3.0.3 | Gráficos históricos de preço e patrimônio, com seleção de períodos e indicação explícita de lacunas e cobertura |

### Preço e patrimônio são métricas diferentes

- **Histórico de preço** acompanha a cotação de um ativo ao longo do tempo; não representa
  o dinheiro ou o resultado de uma carteira individual.
- **Evolução do patrimônio** depende das quantidades efetivamente mantidas em cada data,
  das movimentações e dos preços correspondentes. Aportes e resgates alteram o patrimônio
  sem necessariamente representar rentabilidade. Caixa, proventos, custos, tributos e
  eventos corporativos precisarão de tratamento explícito conforme o escopo disponível.
- Um gráfico de preços não será apresentado como evolução patrimonial. A cotação atual
  não será aplicada retroativamente para inventar patrimônio histórico.

### Dependências e limites

A disponibilidade histórica dependerá de **fontes gratuitas e dados realmente existentes**,
incluindo cobertura, limites, atraso, licença de uso e ajustes de preços. Antes da
implementação, avaliar a viabilidade por fonte e período, sem assumir histórico completo
ou dados em tempo real. Não há compromisso com contratação de serviços pagos.

Períodos sem dados suficientes devem aparecer como indisponíveis/lacunas ou ter a seleção
limitada, sem preencher preços ou rendimentos fictícios. Resumos mensais/anuais devem
definir bases e datas antes de calcular percentuais; fluxo de caixa não é retorno.

Demo pública continuará offline, com séries explicitamente fictícias e separadas das
carteiras privadas. Credenciais de fornecedores continuarão exclusivas do backend.
