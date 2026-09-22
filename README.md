# 🇧🇷 Termômetro Eleições 2026

Aplicativo Android público e experimental para acompanhar **pesquisas presidenciais de 2026**, sua evolução no tempo, incerteza e diferenças entre fontes.

## O que a v0.5.1 faz

- trabalha com **pesquisas individuais** como unidade principal, em vez de somar agregadores;
- deduplica levantamentos pelo número de registro TSE e, quando necessário, por uma chave de conteúdo;
- pondera pesquisas por **recência, tamanho de amostra e repetição do mesmo instituto**;
- calcula uma faixa de incerteza que considera erro amostral aproximado e divergência entre levantamentos;
- mantém primeiro e segundo turno separados;
- reconstrói até **90 dias de histórico** usando somente pesquisas datadas disponíveis;
- mostra tendências observadas em janelas de 5, 15, 30, 60 e 90 dias, sem extrapolar a curva como resultado futuro;
- possui uma aba **Pesquisas** com instituto, data, amostra, método, registro e resultados publicados;
- informa quantidade de pesquisas, institutos, métodos de coleta, registros presentes, idade média e número efetivo de pesquisas após ponderação;
- monitora fontes adicionais de conferência sem dar peso duplo ao mesmo levantamento;
- dá feedback explícito ao botão **Atualizar leitura** quando há nova leitura, quando os percentuais não mudaram ou quando não existe dado novo.
- adiciona uma aba **Diagnóstico** com efeito de instituto/método e validação retrospectiva do agregador;
- calcula diferenças contra pesquisas contemporâneas de outros institutos em janela de ±10 dias;
- mede erro absoluto médio/mediano e cobertura dos intervalos contra a próxima pesquisa publicada;
- mantém esses diagnósticos apenas informativos: **nenhuma correção automática por instituto ou método é aplicada à média atual**.

## Fontes e papéis

### Base estatística

A base atual de pesquisas individuais é extraída da tabela BBC/PollingData. Cada registro é armazenado em data/polls.json antes da agregação.

### Cadastro oficial

O Portal de Dados Abertos do TSE é monitorado como camada de validação de registros:

https://dadosabertos.tse.jus.br/dataset/pesquisas-eleitorais-2026

Se a consulta automatizada ao TSE estiver indisponível, o aplicativo informa fallback. Números de registro presentes nas fontes continuam visíveis, mas não são marcados como diretamente validados.

### Fontes de conferência

UOL Agregador, ElectioLab e páginas públicas do AtlasIntel são monitorados como referências independentes. Eles têm **peso zero** no agregado principal para evitar contar novamente pesquisas que já aparecem na base individual.

### Mercado de previsão

Polymarket aparece apenas como **sinal externo separado**. Seus preços não alteram a média das pesquisas.

## Metodologia v0.5

Para cada data de referência:

1. pesquisas com mais de 30 dias ficam fora da leitura corrente;
2. cada pesquisa registrada entra no máximo uma vez;
3. a recência recebe decaimento exponencial;
4. amostras maiores recebem ajuste pela raiz do tamanho da amostra, com limites para evitar dominância excessiva;
5. várias pesquisas do mesmo instituto recebem penalização de repetição;
6. o apoio agregado é calculado candidato a candidato;
7. a faixa de incerteza combina incerteza amostral aproximada e heterogeneidade entre pesquisas;
8. cenários de segundo turno são agregados separadamente dos cenários de primeiro turno.

A ordem de exibição dos candidatos no aplicativo é neutra e não é usada como ranking do modelo.

## Dados públicos gerados

- data/analytics.json: leitura atual, qualidade, fontes, intervalos e cenários;
- data/analytics-history.json: série histórica observada/reconstruída;
- data/polls.json: pesquisas individuais deduplicadas e seus metadados;
- data/calibration.json: diagnóstico de institutos/métodos e validação retrospectiva;
- data/historical-backtest.json: estudos retrospectivos de ciclos anteriores;
- data/model-lab.json: comparação técnica de fórmulas do agregador.

## Testes e atualização

O workflow **Atualizar dados eleitorais** roda automaticamente e executa testes antes de publicar novos JSONs. Os testes verificam interpretação da célula compacta de instituto/amostra/método, preservação de amostras grandes, deduplicação por registro, escolha do cenário mais completo e contagem de institutos, métodos e registros.

Se os testes ou a validação estrutural falharem, os novos dados não são publicados.

## Android e assinatura

O workflow **Build e publicar APK** compila e assina o APK com a mesma identidade de desenvolvimento estável adotada desde a v0.2.0, permitindo atualização sobre versões posteriores à transição de assinatura.

A release atual é v0.5.1.

## Aviso

**Este aplicativo não é uma pesquisa eleitoral, não representa o TSE e não recomenda voto ou aposta.** As médias e faixas apresentadas são cálculos estatísticos sobre levantamentos publicados e estão sujeitas a erro, diferenças metodológicas e atualização das fontes.

Licença do código: MIT.

## Calibração v0.4

O diagnóstico de fonte compara cada levantamento com pesquisas próximas de outros institutos. Para cada instituto e método são calculados desvio absoluto médio, dispersão dos resíduos e diferenças médias por candidato quando existem comparações suficientes.

A validação retrospectiva usa apenas pesquisas anteriores para formar o agregado e então compara essa leitura com a próxima pesquisa publicada. Isso mede estabilidade operacional do agregador e **não mede acerto do resultado da eleição**.

O backtest com eleições anteriores permanece marcado como não aplicado. Nenhum efeito histórico será usado como correção da leitura de 2026 sem uma base histórica reproduzível e validada separadamente.

## Backtest histórico v0.4.1

Os estudos históricos são executados em pipeline separado da coleta corrente de 2026. A rotina usa as mesmas regras gerais de recência, tamanho amostral e controle de repetição, comparando-as com uma média simples em horizontes de 30, 21, 14, 7, 3 e 1 dia antes da eleição.

Atualmente há dois estudos separados:

- 2018: 38 pesquisas históricas utilizáveis no conjunto comum de candidatos;
- 2022: 79 pesquisas históricas utilizáveis no conjunto comum de candidatos.

Os resultados oficiais servem exclusivamente como referência retrospectiva. Os estudos não alteram automaticamente pesos, médias ou candidatos da leitura de 2026.

O arquivo público é data/historical-backtest.json. O workflow histórico roda diariamente e também quando o código, os testes ou as dependências desse backtest mudam.

## Laboratório de modelos v0.4.2

O laboratório compara fórmulas pré-definidas sem alterar automaticamente o modelo em produção. São avaliados o modelo atual, dois ritmos de decaimento temporal, ausência de peso por amostra, ausência de penalização por repetição e média simples.

Uma variante só é sinalizada para revisão quando reduz o erro histórico e o erro da validação corrente por margem mínima pré-definida, sem regressão relevante em nenhum ciclo histórico. Promoção automática permanece desabilitada.

Na primeira execução, nenhuma variante atingiu simultaneamente todos os critérios. Por isso o modelo de produção foi mantido sem mudanças.

## Robustez e composição v0.5.0

A leitura corrente agora publica uma análise de sensibilidade leave-one-out. Para cada candidato, o sistema recalcula o agregado retirando uma pesquisa por vez e registra a faixa resultante, a maior alteração observada e a diferença entre janelas de 14 e 30 dias. Esse diagnóstico não altera automaticamente o agregado.

A composição das respostas também passou a ser tratada explicitamente. Colunas como brancos, nulos, indecisos, nenhum e outros candidatos são armazenadas quando a fonte as identifica. Qualquer parcela restante é chamada de residual não classificado e não é interpretada automaticamente como indecisão.

Nos cenários de segundo turno, os percentuais brutos permanecem a leitura principal. Uma normalização adicional entre os dois nomes pode ser exibida como transformação matemática auxiliar, acompanhada de aviso explícito de que ela não é projeção de votos válidos.

O schema de data/analytics.json é v4.

## Influência e sinais atípicos v0.5.1

O diagnóstico de influência mede quanto o agregado muda quando uma pesquisa é removida e quando todas as pesquisas de um instituto são removidas da janela atual. O sistema registra a mudança máxima entre candidatos, a mudança média e as diferenças por candidato.

Separadamente, cada levantamento é comparado a pesquisas contemporâneas de outros institutos em uma janela de ±10 dias. Um limiar robusto baseado na distribuição dos desvios da própria janela pode marcar um "sinal atípico". Esse sinal não afirma que a pesquisa está errada, enviesada ou irregular; ele apenas indica distância estatística em relação aos pares disponíveis.

Nenhum desses diagnósticos é usado automaticamente para excluir pesquisas, reduzir peso de institutos ou alterar a leitura principal. O schema de data/analytics.json é v5.
