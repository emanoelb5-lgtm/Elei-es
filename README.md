# 🇧🇷 Termômetro Eleições 2026

Aplicativo Android público e experimental para acompanhar a eleição presidencial brasileira de 2026 por meio de **múltiplos sinais atualizados**.

## O que ele faz

- combina agregadores de pesquisas e mercados de previsão;
- transforma intenção de voto em um sinal probabilístico de vitória;
- atualiza `data/latest.json` automaticamente a cada 15 minutos via GitHub Actions;
- mantém `data/history.json` com as leituras anteriores;
- mostra no Android a probabilidade estimada, a variação em pontos percentuais e um gráfico histórico;
- o botão **Atualizar leitura** sempre consulta o snapshot público mais recente, sem números embutidos na lógica do APK.

## Fontes monitoradas

O coletor tenta usar ElectioLab, BBC/PollingData, UOL Eleições e a API pública do Polymarket. Se uma fonte falha, ela é marcada como `fallback` e sai do cálculo daquela execução. A lista pode ser ampliada sem alterar o APK.

O cadastro oficial das pesquisas pode ser conferido no Portal de Dados Abertos do TSE: https://dadosabertos.tse.jus.br/dataset/pesquisas-eleitorais-2026

## Metodologia v0.1

1. Agregadores de pesquisas disponíveis são combinados com pesos equivalentes.
2. A intenção de voto é convertida em probabilidade por softmax; a temperatura cai conforme a eleição se aproxima.
3. Quando o mercado de previsão está disponível, o resultado final usa 60% do sinal de pesquisas e 40% do mercado.
4. Tudo é normalizado para 100% e comparado à leitura anterior.

Esta fórmula é propositalmente simples e auditável. Ela será calibrada conforme houver histórico suficiente.

## Aviso importante

**Este aplicativo não é uma pesquisa eleitoral, não é uma previsão oficial, não representa o TSE e não recomenda voto ou aposta.** Probabilidades são estimativas experimentais e podem errar.

## Build

O workflow `Build e publicar APK` compila a versão Android e publica `Termometro-Eleicoes-2026-v0.1.0.apk` na Release `v0.1.0`.

Licença do código: MIT.
