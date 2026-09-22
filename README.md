# 🇧🇷 Termômetro Eleições 2026

Aplicativo Android público e experimental para acompanhar **pesquisas presidenciais de 2026**, sua evolução no tempo, incerteza e diferenças entre fontes.

## O que a v0.3.0 faz

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

## Metodologia v0.3

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
- data/polls.json: pesquisas individuais deduplicadas e seus metadados.

## Testes e atualização

O workflow **Atualizar dados eleitorais** roda automaticamente e executa testes antes de publicar novos JSONs. Os testes verificam interpretação da célula compacta de instituto/amostra/método, preservação de amostras grandes, deduplicação por registro, escolha do cenário mais completo e contagem de institutos, métodos e registros.

Se os testes ou a validação estrutural falharem, os novos dados não são publicados.

## Android e assinatura

O workflow **Build e publicar APK** compila e assina o APK com a mesma identidade de desenvolvimento estável adotada desde a v0.2.0, permitindo atualização sobre versões posteriores à transição de assinatura.

A release atual é v0.3.0.

## Aviso

**Este aplicativo não é uma pesquisa eleitoral, não representa o TSE e não recomenda voto ou aposta.** As médias e faixas apresentadas são cálculos estatísticos sobre levantamentos publicados e estão sujeitas a erro, diferenças metodológicas e atualização das fontes.

Licença do código: MIT.
