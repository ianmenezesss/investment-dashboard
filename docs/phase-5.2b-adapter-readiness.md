# Fase 5.2B — Preparação para adaptadores bancários

**Estado local em 29/10/2026:** documentada; sem parser institucional e sem declaração de suporte a qualquer banco/corretora. A 5.2A genérica permanece a interface de entrada transacional para os eventos atualmente suportados.

## Contrato recomendado

Cada adaptador futuro deve ser um parser puro, específico a uma instituição e versão de exportação. Deve converter linhas verificadas para um formato interno explícito, sem rede, credenciais, regras financeiras próprias ou persistência. A saída passa pela prévia, validação, deduplicação e endpoint transacional de [Fase 5.2A](phase-5.2-csv-import.md). Não criar abstração compartilhada adicional até existir ao menos um layout real aprovado.

## Insumos necessários antes do código

1. Arquivo fictício ou fixture anonimizada que mantenha cabeçalhos, delimitadores, codificação, aspas, sinais, separadores decimais e formatos de data.
2. Dicionário de campos e exemplos de cada tipo de movimento; esclarecer se valores são brutos ou líquidos, moeda, sinal, fuso/data e estado pendente/efetivado.
3. Identificador da transação, estabilidade entre exportações e política para estornos, ajustes e linhas repetidas.
4. Regras de conciliação com eventos existentes, limites do parser e casos ambíguos que devem ser rejeitados para revisão humana.
5. Fixtures sem dados pessoais ou financeiros reais, com testes de regressão e validação do titular antes de declarar suporte.

Depois de receber esses insumos, avaliar primeiro se o layout representa eventos 5.1 ou operações de ativos. O importador genérico atual cobre somente aportes, retiradas, dividendos e JCP; compras/vendas, quantidade, preço, taxa e aplicações/resgates exigem contratos e validação financeira separados.
