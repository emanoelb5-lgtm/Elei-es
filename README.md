# 🇧🇷 Termômetro Eleições 2026

Aplicativo Android para acompanhar **somente o segundo turno presidencial de 2026**, entre Flávio Bolsonaro (PL) e Lula (PT), com votação em 25 de outubro.

## Versão 0.10.0

- Mostra pesquisas realizadas após 4 de outubro entre os dois finalistas, com instituto, data, amostra, método, registro informado e link da fonte.
- Identifica **votos totais** e **votos válidos** em separado. Não mistura as bases nem transforma pesquisas em previsão do resultado.
- Exibe uma tela inicial clara, lista de pesquisas com busca e filtros, e uma aba que explica os dados.
- Mantém a última leitura do segundo turno no aparelho para consulta sem conexão após a primeira atualização.

A leitura pública usada pelo aplicativo está em [data/runoff-2026.json](data/runoff-2026.json). [data/runoff-curated.json](data/runoff-curated.json) registra levantamentos conferidos nas publicações de Datafolha e PoderData. O script [scripts/update_runoff.py](scripts/update_runoff.py) incorpora novas linhas da tabela BBC/PollingData somente quando a coleta ocorreu após o primeiro turno e contém exatamente os dois finalistas. Se a base percentual da tabela não está documentada, ela aparece como **base a conferir**. A atualização automática roda no GitHub Actions e valida os dados antes da publicação.

O [TSE confirmou os finalistas](https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/flavio-bolsonaro-e-lula-vao-disputar-o-2o-turno-para-a-presidencia-da-republica). O código e os dados legados de agregação permanecem no repositório para auditoria histórica, mas a interface desta versão não os usa.

## APK

Baixe a versão atual na [Release v0.10.0](https://github.com/emanoelb5-lgtm/Elei-es/releases/tag/v0.10.0). O workflow **Build e publicar APK** compila e assina o pacote com a mesma identidade de desenvolvimento adotada desde a v0.2.0. Esta chave de teste é destinada a desenvolvimento, não à Play Store.

**Este aplicativo não é uma pesquisa eleitoral, não representa o TSE e não recomenda voto ou aposta.** Consulte o método e a publicação original de cada levantamento.

Licença: MIT.
