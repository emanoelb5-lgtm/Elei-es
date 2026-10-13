# Termômetro Eleições 2026

Aplicativo Android para acompanhar somente o **segundo turno presidencial** entre Flávio Bolsonaro e Lula.

## Funcionamento na versão 0.11.0

1. Abre com uma base conferida incluída no APK, mesmo na primeira instalação sem internet.
2. Consulta um único painel de dados, tenta um segundo endereço se necessário e conserva a leitura disponível quando a rede falha ou a resposta é inválida.
3. O botão **Atualizar pesquisas** compara as evidências, não o horário do arquivo. Informa quando não há pesquisa nova.
4. **Início:** chance exploratória no modelo, apoio agregado em votos válidos, intervalo de cenário, variação, pesquisa mais recente e mercado de previsão separado.
5. **Pesquisas:** resultados publicados, período da coleta, divulgação, amostra, método, margem de erro, busca, filtros e publicação original.
6. **Evolução:** apoio e chance no modelo por datas de divulgação, incluindo histórico anterior à instalação. Não inventa pontos nos dias sem publicação.
7. **Fontes:** metodologia, pesquisas e pesos usados e disponibilidade das fontes.

## Modelo e limites

Apenas pesquisas com coleta integral a partir de 05/10/2026 entre os dois finalistas. O agregado usa um levantamento por instituto, janela de 14 dias, recência com meia-vida de sete dias e peso amostral limitado. Votos válidos publicados têm prioridade; a conversão de votos totais, quando necessária, é explicitamente identificada. Base desconhecida não entra no modelo.

A probabilidade de vitória é **exploratória, não calibrada**: aplica uma distribuição normal ao apoio agregado, com piso de desvio estrutural de três pontos de votos válidos, dispersão entre institutos, horizonte até o pleito e idade da coleta. O intervalo de cenário também depende dessas hipóteses; não é a margem de erro de uma pesquisa. Duas datas iniciais não comprovam tendência. O app não representa o TSE nem recomenda voto.

Cotações recentes de Polymarket são mostradas como sinal externo; não se somam aos votos nem recebem peso na estimativa do aplicativo.

## Dados e atualização

- [runoff-curated.json](data/runoff-curated.json): pesquisas conferidas nas publicações originais.
- [runoff-dashboard.json](data/runoff-dashboard.json): painel, diagnóstico, histórico, fontes e mercado.
- [runoff-2026.json](data/runoff-2026.json): feed compatível com a versão 0.10.0.
- [update_runoff.py](scripts/update_runoff.py): pipeline independente do primeiro turno. Conserva evidências confirmadas quando fontes complementares falham.
- GitHub Actions verifica as fontes a cada 15 minutos; disponibilidade de publicação e execução pode variar. O app sincroniza na abertura e a cada cinco minutos enquanto está ativo.

A data da coleta, a consulta pelo coletor e a consulta pelo aparelho são exibidas separadamente.

## Verificação e APK

O workflow de publicação executa testes Python, testes Kotlin, Android Lint e testes de abertura offline, navegação, atualização sem mudança e recuperação de cache no emulador Android 15 antes de assinar e publicar o APK.

[Baixar APK v0.11.0](https://github.com/emanoelb5-lgtm/Elei-es/releases/download/v0.11.0/Termometro-Eleicoes-2026-v0.11.0.apk)

A assinatura de desenvolvimento permanece compatível com as versões desde a v0.2.0. Não é uma chave destinada à Play Store.

Licença: MIT.
