# 🇧🇷 Termômetro Eleições 2026

Aplicativo Android público e experimental para acompanhar **pesquisas presidenciais de 2026**, sua evolução no tempo, incerteza e diferenças entre fontes.

## O que a v0.9.5 faz

- abre a última leitura salva no aparelho enquanto consulta as fontes, inclusive sem conexão após a primeira atualização;
- mostra a data da leitura e avisa quando histórico ou diagnósticos não puderem ser atualizados;
- traz início reorganizado, cartões legíveis em celulares menores e navegação com ícones;
- mantém a metodologia de cálculo da v0.9.4.

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

A release atual é v0.9.5.

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

## Incerteza avançada v0.6.0

A faixa principal exibida no primeiro turno passa a combinar três componentes independentes:

1. intervalo analítico do agregador, baseado em erro amostral aproximado e heterogeneidade entre pesquisas;
2. bootstrap determinístico das pesquisas da janela corrente, com percentis de reamostragem;
3. piso empírico baseado no percentil 80 do erro absoluto observado na validação retrospectiva contra a próxima pesquisa publicada. Quando há volume suficiente, esse piso é calibrado separadamente por faixa de apoio (baixo, médio ou alto); caso contrário, usa o quantil global.

O aplicativo preserva os três componentes separadamente para auditoria. A faixa avançada usa o componente mais conservador e nunca fica artificialmente mais estreita que o intervalo analítico anterior.

O bootstrap mede sensibilidade da estimativa de apoio atual à composição da amostra de pesquisas. O piso empírico mede capacidade de reprodução observada em leituras passadas. Nenhum dos dois representa chance de vitória, probabilidade eleitoral ou previsão de resultado futuro.

O schema de data/analytics.json passa a ser v6.

Na validação corrente usada para verificar a v0.6.0, o intervalo analítico anterior cobriu 52,3% das observações retrospectivas. A calibração empírica por faixa atingiu 79,8% de cobertura para q80 e 89,8% para q90. Esses percentuais medem reprodução de pesquisas passadas, não acerto de eleição futura.

## Bootstrap por instituto v0.6.1

A incerteza avançada passa a usar dois processos de reamostragem em paralelo:

- bootstrap por pesquisa: sorteia levantamentos individuais da janela;
- bootstrap em blocos por instituto: sorteia institutos e mantém juntas as pesquisas pertencentes ao mesmo bloco.

O segundo processo reduz a hipótese de independência entre levantamentos do mesmo instituto. Se o bootstrap por instituto produzir uma faixa mais larga que os demais componentes, ele pode determinar a largura final. O aplicativo mostra qual componente foi determinante, sem alterar os pesos das pesquisas nem excluir fontes.

Nos cenários de segundo turno, o aplicativo também usa intervalo analítico, bootstrap por pesquisa e bootstrap por instituto. O piso empírico calibrado no primeiro turno não é reaproveitado nos confrontos, porque a distribuição de erro pode ser diferente.

O schema de data/analytics.json passa a ser v7. Nenhum componente calcula chance de vitória ou previsão própria de resultado eleitoral.

## Mudança de regime v0.7.0

O agregador ganhou um detector de mudança de patamar que compara duas janelas independentes: os últimos 7 dias e o bloco anterior de 8 a 30 dias.

O diagnóstico só é executado quando existem pelo menos 4 pesquisas recentes de 3 institutos e pelo menos 6 pesquisas anteriores de 3 institutos. Para cada candidatura são calculados:

- apoio agregado no bloco recente;
- apoio agregado no bloco anterior;
- diferença em pontos percentuais;
- razão entre o deslocamento e a incerteza combinada das duas janelas;
- consistência da direção entre os institutos recentes.

O detector classifica cada série como estável, em observação ou com deslocamento consistente. Essa classificação descreve mudança entre blocos de pesquisas e não é uma previsão de resultado eleitoral.

Uma leitura adaptativa é calculada apenas em sombra. Quando há sinal, ela dá peso adicional ao bloco recente, mas não substitui o agregado exibido. Uma validação retrospectiva compara essa versão em sombra com o modelo normal contra a pesquisa seguinte. A adaptação só fica tecnicamente elegível para revisão se houver volume mínimo de casos e redução de pelo menos 0,10 p.p. no erro absoluto médio. Mesmo assim, nenhuma promoção é automática.

O schema de data/analytics.json passa a ser v8.

## Persistência temporal v0.7.1

O detector de mudança de regime passou a exigir persistência entre conjuntos distintos de pesquisas.

Cada conjunto de evidências recebe um fingerprint determinístico construído a partir das pesquisas da janela corrente, incluindo data, instituto, amostra, método, registro e resultados. Uma nova execução do pipeline com exatamente os mesmos dados mantém o mesmo fingerprint e não aumenta o contador de persistência.

Para cada candidatura com sinal de mudança:

- 1 estado distinto na mesma direção: não confirmado;
- 2 estados distintos consecutivos: ganhando persistência;
- 3 ou mais estados distintos consecutivos: persistente.

Se a direção se inverter ou o detector voltar a estável, a sequência é interrompida. O histórico compacto dessas evidências fica em data/regime-history.json.

A persistência continua exclusivamente diagnóstica. Ela não altera pesos, médias, intervalos ou a leitura adaptativa em sombra.

O schema de data/analytics.json passa a ser v9.

## Diversidade metodológica v0.8.0

A incerteza avançada passa a considerar também dependência entre pesquisas que usam o mesmo método de coleta.

Os métodos são normalizados em grupos operacionais: presencial, telefônica/CATI, online/digital, URA/IVR, híbrida e outros. A composição metodológica é calculada usando os pesos efetivos das pesquisas da janela, não apenas sua contagem bruta.

O sistema publica:

- número de métodos distintos;
- número efetivo de métodos, derivado da concentração dos pesos;
- maior participação de um método na janela;
- índice de concentração metodológica;
- participação ponderada de cada grupo;
- 500 reamostragens bootstrap em blocos por método, quando há diversidade suficiente.

A faixa avançada pode ser determinada pelo bootstrap por método se ele for mais conservador que intervalo analítico, bootstrap por pesquisa, bootstrap por instituto e piso empírico. Nenhum método recebe bônus, penalização ou correção automática.

O schema de data/analytics.json passa a ser v10.

## Frescor e cobertura temporal v0.8.1

A leitura corrente passou a medir não apenas quantas pesquisas existem, mas como elas estão distribuídas no tempo.

O diagnóstico calcula:

- idade da pesquisa mais recente;
- mediana ponderada da idade das pesquisas;
- idade que concentra 80% do peso acumulado;
- participação do peso efetivo vindo dos últimos 7 e 14 dias;
- número de datas distintas com pesquisas;
- número de dias ativos nos últimos 14 dias;
- número efetivo de datas após ponderação;
- maior concentração de peso em uma única data;
- amplitude temporal da janela;
- maior lacuna entre datas de levantamentos.

O frescor é classificado como fresco, moderado ou defasado, e a cobertura por data como diversificada, moderada ou concentrada. Essas classificações descrevem a base corrente e não alteram automaticamente o peso temporal das pesquisas.

O schema de data/analytics.json passa a ser v11.

## House effect em sombra v0.9.0

O aplicativo passa a testar uma correção de efeito de instituto sem alterar a leitura principal.

Para cada instituto e candidatura, o sistema estima diferenças médias em relação a pesquisas contemporâneas de outros institutos. Esses offsets só são considerados quando há comparações mínimas suficientes, recebem shrinkage em direção a zero e têm magnitude máxima limitada.

A leitura corrigida é executada apenas em sombra. A validação é temporal: para avaliar uma pesquisa futura simulada, os offsets são aprendidos exclusivamente com pesquisas anteriores àquela data. Isso evita vazamento de informação futura para o teste.

A validação compara MAE do modelo atual com MAE da versão corrigida em sombra. Uma eventual melhora só torna a técnica elegível para revisão; nenhuma correção é ativada automaticamente.

O schema de data/analytics.json passa a ser v12.

## Cobertura de candidaturas e cenários v0.9.1

Pesquisas diferentes podem testar conjuntos diferentes de candidaturas. A v0.9.1 passa a medir explicitamente esse problema em vez de interpretar a ausência de um nome como 0%.

Para cada candidatura são publicados:

- número de pesquisas em que aparece;
- número de institutos e métodos que a medem;
- participação ponderada do peso da janela;
- indicação de pertencimento ao conjunto comum de candidaturas.

O conjunto comum é definido por cobertura ponderada mínima de 80%. A análise também registra quantas combinações de candidaturas existem, o peso do cenário dominante e a parcela da base preservada numa harmonização.

Uma leitura harmonizada em sombra usa apenas pesquisas que contêm todo o conjunto comum, mas preserva os pesos originais dessas pesquisas. Isso permite medir o quanto a mistura de cenários desloca o agregado sem confundir o efeito com uma recalibração dos pesos.

A harmonização também recebe validação temporal contra pesquisas posteriores. Nenhuma pesquisa é excluída automaticamente e a leitura principal permanece inalterada.

O schema de data/analytics.json passa a ser v13.

## Auditoria dos pesos v0.9.2

O aplicativo passa a publicar uma decomposição exata do peso aplicado a cada pesquisa da janela corrente.

A fórmula auditada é a mesma função usada pelo agregador:

peso bruto = fator de recência × fator amostral × penalização por repetição do instituto × fator de validação TSE.

Para cada levantamento são expostos idade, fatores individuais, quantidade de pesquisas do mesmo instituto na janela, peso bruto e participação relativa no peso total da janela.

Como nem todas as pesquisas testam exatamente o mesmo conjunto de candidaturas, a auditoria também calcula a participação específica de cada levantamento dentro do agregado de cada candidatura. O denominador considera somente pesquisas em que aquela candidatura foi efetivamente testada; ausência de nome não equivale a zero.

A lista permanece em ordem cronológica e não é ordenada por peso. A auditoria não adiciona bônus, penalidade ou correção além das regras já existentes no agregador.

O schema de data/analytics.json passa a ser v14.

## Stress test dos pesos v0.9.3

A auditoria exata da v0.9.2 passa a ser complementada por um stress test paramétrico da fórmula de ponderação.

São calculadas sete configurações pré-definidas, sem alterar outros componentes do modelo:

- configuração de produção;
- recência mais rápida;
- recência mais lenta;
- peso amostral mais fraco;
- peso amostral mais forte;
- penalização por repetição mais fraca;
- penalização por repetição mais forte.

Para cada candidatura, o sistema publica a leitura de produção, mínimo e máximo entre as configurações, amplitude total e maior deslocamento em relação à produção.

A configuração chamada Produção usa exatamente os mesmos parâmetros e a mesma lógica do agregador corrente. Os testes automatizados exigem que ela reproduza a leitura principal numericamente.

O stress test mede dependência das escolhas paramétricas. Nenhuma variante é considerada vencedora, nenhuma é promovida automaticamente e a ordem de exibição não constitui ranking.

O schema de data/analytics.json passa a ser v15.

## Incerteza paramétrica v0.9.4

O stress test de pesos da v0.9.3 passa a contribuir diretamente para a faixa de incerteza, sem alterar a leitura central.

Para cada candidatura, as sete configurações pré-definidas de ponderação produzem um envelope mínimo–máximo. A distância máxima desse envelope em relação ao valor de produção é tratada como um componente adicional de incerteza.

A faixa avançada passa a considerar, em paralelo:

- intervalo analítico;
- bootstrap por pesquisa;
- bootstrap por instituto;
- bootstrap por método;
- envelope paramétrico da fórmula de pesos;
- piso empírico q80, quando aplicável.

O maior desses componentes define a largura final. Nenhuma variante paramétrica é escolhida, ranqueada ou aplicada à estimativa central.

O schema de data/analytics.json passa a ser v16.
