# Contrato de catálogo comum, versão 1

Este documento é o mesmo, palavra por palavra, nos quatro geradores irmãos: Carcará (mapa), Andorinha (rotas), Sabiá
(busca) e Pardal (radares e limites). Ele descreve um bloco que os quatro escrevem no próprio `catalogo.json`, com os
mesmos nomes e o mesmo sentido, para que um único leitor (num aplicativo Android, numa página web ou num GIS) descubra,
baixe, confira e instale os pacotes de qualquer um deles sem conhecer as particularidades de cada gerador.

O esquema JSON do bloco está em [`catalogo-v1.schema.json`](catalogo-v1.schema.json), também idêntico nos quatro.
As particularidades de cada gerador estão no fim: [Carcará](#carcara), [Andorinha](#andorinha), [Sabiá](#sabia) e
[Pardal](#pardal).

## Onde fica: a chave `contract`

O bloco é a chave `contract` no nível de cima do `catalogo.json`. Tudo o que um leitor genérico precisa está dentro
dela; as outras chaves do catálogo continuam como eram e servem aos leitores que já existem.

**Regra de ouro: só acrescentar.** O contrato não muda nome, tipo nem sentido de nenhuma chave que já existia no
catálogo de cada gerador, e não remove nenhuma. Por isso ele mora numa chave nova, em vez de corrigir as antigas: o
`schema` de cada catálogo (1 em três deles, 2 no Pardal) segue igual, o `generator_commit` curto continua curto, o
`bbox` continua onde estava. Os valores que se repetem (o `build_id`, por exemplo) são iguais aos das chaves antigas,
e os testes de cada gerador conferem isso.

**Leitores ignoram o que não conhecem.** Um leitor do contrato v1 ignora, sem erro, qualquer chave que não esteja
descrita aqui, em qualquer nível. É isso que deixa o contrato crescer sem quebrar quem já lê.

## Versões

| Chave | Tipo | Sentido |
|---|---|---|
| `name` | texto | Sempre `"catalogo-comum"`: identifica esta especificação. |
| `version` | inteiro | A versão do contrato que o catálogo segue. Hoje, 1. Acréscimo compatível (chave nova, valor novo numa lista aberta) não muda a versão. |
| `min_reader_version` | inteiro | A menor versão de leitor que consegue usar o catálogo. Um leitor da versão R usa o catálogo se `min_reader_version <= R` e recusa se for maior ("atualize o leitor"). Hoje, 1. |

`version` diz o que o catálogo **pode** trazer; `min_reader_version` diz o que o leitor **precisa** entender. Uma
versão 2 que só acrescenta continua com `min_reader_version` 1. Uma mudança que um leitor antigo leria errado em
silêncio sobe `min_reader_version` e usa um nome de chave novo, nunca o mesmo nome com outro sentido.

## O catálogo

| Chave | Tipo | Sentido |
|---|---|---|
| `name`, `version`, `min_reader_version` | | Ver [Versões](#versões). |
| `dataset` | texto | O conjunto de dados: `carcara`, `andorinha`, `sabia` ou `pardal`. |
| `build_id` | texto | A geração, no formato `AAAA-MM-DD-xxxxxxxx` (data e 8 dígitos hexadecimais). Igual ao `build_id` antigo onde ele existe. |
| `built_at` | texto | Quando a geração foi feita, ISO 8601 em UTC (`2026-11-09T01:15:23Z`). |
| `release_url` | texto | A pasta da release desta geração, absoluta, terminando em `/`. Informativa: a URL de cada arquivo vem pronta em `files`. |
| `generator` | objeto | `repository`: a URL do repositório do gerador; `commit`: o SHA **completo** (40 dígitos) do commit que gerou a geração (`null` só fora de um checkout do git). |
| `license` | objeto | `data`: a licença dos dados em SPDX; `code`: a do código do gerador em SPDX; `attribution`: o crédito que precisa aparecer junto dos dados. Um arquivo com licença própria a declara em `files[].license`. |
| `coordinates` | objeto | `crs`: sempre `"EPSG:4326"` (WGS84); `bbox_order`: sempre `"lat_min,lon_min,lat_max,lon_max"`. |
| `osm_snapshot` | objeto | A foto do OpenStreetMap por trás dos dados: `date` (texto ou `null`) e `md5` do extrato (texto ou `null`). É a chave para comparar a idade dos dados entre os geradores (ETD §7.7). |
| `sources` | lista | As fontes de entrada que o gerador conhece, com data e checksums (ver [Fontes](#fontes-d-12)). |
| `compatibility` | objeto | O que é preciso para abrir os dados (ver [Compatibilidade](#compatibilidade)). |
| `files` | lista | Os arquivos da geração, todos no mesmo formato (ver [Arquivos](#arquivos)). |

## Arquivos

Cada item de `files` é um arquivo que se baixa e confere sozinho.

| Chave | Tipo | Sentido |
|---|---|---|
| `id` | texto | Único no catálogo e estável entre gerações (o mesmo pacote tem o mesmo `id` na geração seguinte). Letras, dígitos, `.`, `_`, `-` e `/`. |
| `kind` | texto | O papel do arquivo (tabela abaixo). |
| `region` | texto ou `null` | A UF (`"GO"`), `"BR"` para o país inteiro, `null` para arquivo sem área (recursos, estilo, testes). |
| `url` | texto | URL **absoluta** (`https://`) de onde baixar os bytes. |
| `sha256` | texto | sha256 dos bytes do arquivo (64 dígitos hexadecimais, minúsculos). **Obrigatório**: o instalador confere sempre. |
| `bytes` | inteiro | Tamanho do arquivo, em bytes. |
| `bytes_unpacked` | inteiro ou `null` | Soma dos tamanhos depois de desempacotar (`unpack`), quando o arquivo é compactado e o gerador sabe; `null` quando não se aplica ou não se sabe. |
| `media_type` | texto | O tipo de mídia dos bytes baixados (`application/zstd`, `text/csv`, `application/vnd.pmtiles`...). |
| `unpack` | lista | Os passos para ir dos bytes baixados ao que se usa, na ordem: `"gzip"`, `"zstd"`, `"tar"`, `"zip"`. Lista vazia: usa-se o arquivo como veio. |
| `format` | texto | O formato do conteúdo depois de desempacotado (ex.: `pmtiles`, `valhalla-tiles`, `sqlite`, `csv`). Os valores de cada gerador estão nas particularidades. |
| `bbox` | lista ou `null` | `[lat_min, lon_min, lat_max, lon_max]` em graus WGS84, a área que o arquivo atende, arredondada para fora; `null` para arquivo sem área. |
| `coverage_level` | texto ou `null` | O nível de cobertura que o arquivo dá à sua área (ver [Níveis de cobertura](#níveis-de-cobertura)); `null` para arquivo sem área ou que não é dado do mapa, da rota, da busca ou dos alertas (ex.: os polígonos das UFs). |
| `requires` | lista | Os `id` de outros arquivos **deste catálogo** sem os quais este não serve. Lista vazia: serve sozinho. |
| `container`, `member` | texto (opcionais) | O arquivo também (ou só) é publicado dentro de outro: `container` é o `id` do arquivo que o contém (um zip) e `member` o caminho lá dentro. Se `url` é a mesma do contêiner, o arquivo só se obtém por ele: baixe o contêiner, confira o sha256 dele, extraia `member` e confira o sha256 do membro (`sha256` e `bytes` são sempre os do próprio arquivo). Se é outra, ela baixa o arquivo direto. |
| `license` | texto (opcional) | SPDX deste arquivo, quando não é a de `license.data`. |

Os valores de `kind`:

| `kind` | O que é |
|---|---|
| `base` | A camada nacional que liga os estados (malha principal, visão geral). Sozinha não dá cobertura detalhada. |
| `uf` | Um estado, completo. |
| `uf_light` | Um estado numa versão menor (menos zoom, por exemplo). |
| `national` | O país inteiro num arquivo só, com o detalhe dos estados. |
| `resources` | Recursos sem área que os outros arquivos pedem (fontes, ícones). |
| `style` | Um estilo pronto para desenhar os dados (reservado: nenhum gerador publica ainda). |
| `conformance` | Casos de teste de conformidade para quem reimplementa a leitura (o Sabiá publica). |
| `auxiliary` | Arquivo de apoio (ex.: os polígonos das UFs). |

Um leitor que encontra um `kind`, um `format` ou um passo de `unpack` que não conhece **ignora aquele arquivo** e
segue com os outros. Um gerador pode pôr chaves próprias num arquivo (o zoom no Carcará, `content` no Pardal); elas
estão nas particularidades.

## Níveis de cobertura

Os níveis são os da ETD (§7.5). `PARTIAL` e `UNAVAILABLE` descrevem o que o aplicativo tem instalado num momento, não
um arquivo; por isso só os dois primeiros aparecem no catálogo.

| Nível | Quando o catálogo usa |
|---|---|
| `DETAILED` | O arquivo cobre a área com o detalhe completo do gerador: os pacotes de estado (`uf`, `uf_light`) e os nacionais completos (`national`). |
| `BASE_HIGHWAYS_ONLY` | O arquivo é a camada nacional de ligação (`base`): só a malha principal ou a visão geral. Serve para trechos intermediários entre pontas cobertas; origem, destino e paradas precisam de `DETAILED`. |

O pacote leve do Carcará é `DETAILED`: cobre o estado inteiro, só que até um zoom menor (o zoom vem nos campos próprios
dele). As três bases (mapa até o zoom 9, rotas só no nível 0 do Valhalla, busca só com municípios e rodovias) são
`BASE_HIGHWAYS_ONLY`: nas três, a base sozinha não basta para começar ou terminar uma viagem.

## Fontes (D-12)

Só a geração corrente é reproduzível (decisão D-12 da ETD); o catálogo registra, de cada fonte de entrada que o
gerador conhece, o que permite conferir que a geração usou aquela entrada.

| Chave | Tipo | Sentido |
|---|---|---|
| `id` | texto | Nome curto da fonte (`openstreetmap`, `ibge-malha-uf`...). |
| `name` | texto (opcional) | Nome legível. |
| `url` | texto ou `null` (opcional) | De onde a entrada veio. |
| `date` | texto ou `null` | Data (`AAAA-MM-DD`) ou data e hora (ISO 8601 UTC) do dado, quando a fonte informa. |
| `version` | texto (opcional) | A versão ou edição, quando a fonte tem uma. |
| `license` | texto ou `null` (opcional) | SPDX da fonte, quando é conhecido e tem identificador. |
| `checksums` | objeto | Os checksums que o gerador conhece, por algoritmo: `sha256`, `md5` ou `b3sum` (BLAKE3), em hexadecimal. Pode ser vazio. |
| `note` | texto (opcional) | O que o checksum cobre, quando não é o arquivo baixado (ex.: o conteúdo descompactado). |

Fonte que o gerador baixa sem guardar data nem checksum não aparece (ou aparece sem checksum): o contrato não inventa
o que o gerador não sabe.

## Compatibilidade

| Chave | Tipo | Sentido |
|---|---|---|
| `mix_generations` | booleano | `true`: arquivos de gerações diferentes podem ser usados juntos. `false`: todos os arquivos ativos têm de ter o mesmo `build_id`. |
| `data_format` | objeto | `name` e `version` (texto) do formato dos dados. |
| `carcara`, `andorinha`, `sabia`, `pardal` | objeto | O bloco do gerador (`dataset`), com o que o motor que lê os dados precisa. Só o do próprio gerador aparece. |

## Como um leitor instala

O fluxo é o da ETD (§7.6), igual para os quatro:

1. Ler o `catalogo.json` e a chave `contract`. Sem ela, ou com `name` diferente de `catalogo-comum`, o catálogo não
   segue este contrato. Recusar se `min_reader_version` for maior que a versão do leitor.
2. Conferir `compatibility`: o `data_format` e o bloco do gerador (no Andorinha, a versão do Valhalla).
3. Escolher os arquivos pela `region`, pelo `bbox` (latitude primeiro) e pelo `kind`, e juntar os `requires`.
4. Calcular o espaço: `bytes` + `bytes_unpacked` (ou `bytes`, quando é `null`) + a versão anterior, e recusar se faltar.
5. Baixar cada `url` para uma área provisória e conferir `bytes` e `sha256`; para membro de contêiner, conferir o
   contêiner e depois o membro.
6. Desempacotar na ordem de `unpack`.
7. Validar o conjunto: os `requires` presentes e, se `mix_generations` for `false`, o mesmo `build_id` em tudo.
8. Ativar por troca atômica e manter a versão anterior até a próxima ativação válida.

## Diferenças em relação à ETD (§7.3)

A ETD propõe nomes de campo; o contrato usa os dela, menos onde havia motivo para outro:

- **Uma chave nova (`contract`) em vez de campos soltos no topo.** A ETD sobe o `schema`; aqui o `schema` antigo não
  pode mudar (os leitores atuais recusam outro número), e `generator_commit`, `bbox` e `base_url` já existem com outro
  sentido ou outro formato. Uma chave nova não quebra ninguém.
- **`dataset` em vez de `engine`.** "Motor", nos blocos de compatibilidade, é o programa que lê os dados (Valhalla,
  SQLite); o nome do conjunto ficou com outra palavra para não confundir.
- **`generator.commit` em vez de `generator_commit`.** O antigo é o hash curto e continua assim; o completo precisava
  de outro lugar.
- **`license` (dados, código e atribuição) em vez de `licenses` por fonte.** A licença de cada fonte vai em
  `sources[].license`, quando conhecida; muitas fontes públicas não têm identificador SPDX, e o contrato não inventa.
- **`min_reader_version` em vez de `min_app_version`.** O catálogo não conhece nenhum aplicativo; o que ele sabe é a
  versão do contrato que o leitor precisa entender.
- **`files` em vez de `packages`, com `kind` em inglês** (`uf_light`, `resources`, em vez de `leve`, `recursos`),
  para valores e chaves ficarem na mesma língua. `size` e `size_unpacked` viraram `bytes` e `bytes_unpacked`, o nome
  que os catálogos já usam.
- **`unpack`, `media_type` e `format` por arquivo**, que a ETD não tem: sem eles, o leitor genérico precisaria
  conhecer cada gerador para descompactar.
- **`source_dates` virou `sources`**, uma lista com data e checksums, porque a D-12 pede o sha256 das entradas e a
  data sozinha não basta.
- **O bloco de cada gerador fica dentro de `compatibility`**, em vez de no topo.
- **O catálogo não traz o próprio sha256**: um arquivo não contém o próprio hash. A release publica o `catalogo.json`
  como anexo; assinatura fica para depois.

## Uma geração já publicada

Cada gerador tem `gerador/scripts/recatalog.py`, que acrescenta o bloco ao catálogo de uma geração já publicada sem
refazer os dados: lê o catálogo (e, no Pardal, o `SHA256SUMS.txt` da release), resolve o commit completo no git e
grava o resultado num arquivo à parte, para conferir antes de trocar o `catalogo.json`. Os checksums das entradas vêm
da configuração do gerador **no commit da geração**: o que só entrou depois fica de fora.

## Esquema e testes

[`catalogo-v1.schema.json`](catalogo-v1.schema.json) descreve o bloco (JSON Schema 2020-12). Ele aceita chaves a mais,
como manda a regra dos leitores. Cada gerador tem testes que montam um catálogo com o código atual e conferem: o
formato do bloco contra o esquema, as regras que o esquema não expressa (ids únicos, `requires` e `container` que
existem, ordem do `bbox`), as URLs absolutas, os sha256 iguais aos das chaves antigas e, no Andorinha, as versões
amarradas à configuração do gerador. Os testes também conferem o sha256 deste documento e do esquema: mudou um, muda
igual nos quatro repositórios.

## Particularidades

<a id="carcara"></a>

### Carcará

- **Arquivos:** `base` (o Brasil do zoom 0 ao 9), um `uf` por estado (zoom 0 a 15), um `uf_light` por estado (zoom 0
  a 13, `id` `<UF>-leve`) e `resources` (`id` `recursos`: fontes e ícones). Os de tiles têm também `minzoom`, `maxzoom`
  e `tiles`.
- **Formato:** `format` `pmtiles` (`media_type` `application/vnd.pmtiles`, `unpack` vazio, `bytes_unpacked` `null`):
  PMTiles v3 com tiles MVT comprimidos em gzip. Os recursos são `glyphs-sprites` (`application/gzip`, `unpack`
  `["gzip", "tar"]`), sob `OFL-1.1 AND MIT`.
- **`requires`:** os pacotes de tiles pedem `recursos` (rótulos e ícones). A base não é exigida, mas sem ela não há
  mapa fora dos estados instalados.
- **`mix_generations`:** `true` (pacotes de gerações diferentes convivem; o pior caso é uma emenda na divisa).
- **`compatibility.carcara`:** `tileset` (`name` `protomaps-basemap`, `version` exata e `major` 4), `pmtiles_version`
  3, `tile_type` `mvt`, `tile_compression` `gzip`, `glyphs` e `sprites` (`file`, o `id` do arquivo que os traz;
  `template`, o caminho dentro dele; e as fontes e variações publicadas).
- **`osm_snapshot`:** a data do OpenStreetMap do build da Protomaps; sem `md5` (a Protomaps publica o BLAKE3 do
  build, que vai em `sources`).
- **Estilo pronto:** quando sair, entra como um arquivo `kind` `style`, `format` `maplibre-style`, `media_type`
  `application/json`, `region` `null` e `requires` `["recursos"]`.

<a id="andorinha"></a>

### Andorinha

- **Arquivos:** `base` (o nível 0 do Valhalla, só rodovias principais) e um `uf` por estado (níveis 1 e 2). `format`
  `valhalla-tiles`, `media_type` `application/zstd`, `unpack` `["zstd", "tar"]`; `bytes_unpacked` é a soma dos
  tiles.
- **`requires`:** cada estado pede `base`.
- **`mix_generations`:** `false`: nunca juntar `build_id` diferentes na pasta ativa.
- **`compatibility.andorinha`:** `engine` `valhalla`, `valhalla_engine_version` (3.9.1), `valhalla_commit` (SHA
  completo da tag), `tile_format_version` (o texto que o cabeçalho de cada tile traz, no deslocamento 0x10),
  `valhalla_mobile_version` (a biblioteca Android/iOS que embute esse mesmo commit), `valhalla_mobile_artifact` e
  `valhalla_mobile_aar_sha256` (o AAR conferido), `valhalla_mobile_abis` (as ABIs que a biblioteca traz) e
  `required_config` (igual à chave `required_config` do topo, que continua valendo). Todos vêm de
  `gerador/andorinha/config.py`; um leitor recusa a geração se `tile_format_version` não for a do motor dele.
- **`sources`:** o extrato do OpenStreetMap (`md5`), a cópia da malha das UFs do IBGE (`sha256`) e o zip de fusos do
  timezone-boundary-builder (`sha256`).

<a id="sabia"></a>

### Sabiá

- **Arquivos:** `base` (municípios e rodovias do país) e um `uf` por estado. `format` `sqlite`, `media_type`
  `application/zstd`, `unpack` `["zstd"]`; `bytes_unpacked` é o tamanho do banco.
- **`requires`:** nenhum: cada estado é independente; a base serve quando o estado da cidade não está instalado.
- **`mix_generations`:** `true` (o `build_id` de cada banco está na tabela `meta`).
- **`compatibility.sabia`:** `format_version` (o `meta.format_version` dos bancos; recuse maior), `sqlite_min_version`
  (3.22.0), `sqlite_modules` (`fts4`), `sqlite_not_used` (`fts5`, `rtree`) e os endereços, fixados no commit da
  geração, do formato (`format_spec`), da busca (`search_spec`) e da implementação de referência
  (`search_reference`).
- **`sources`:** o extrato do OpenStreetMap (`md5`) e as cópias versionadas no repositório (malha e lista de municípios
  do IBGE, marcos do SNV, aeródromos da ANAC, postos da PRF), com o sha256 do conteúdo descompactado.
- **Conformidade:** o conjunto de casos de teste da busca, para quem reimplementa a leitura (`docs/CONFORMIDADE.md`
  do Sabiá), é o arquivo `id` `conformidade`, `kind` `conformance`, `format` `sabia-search-cases`, `media_type`
  `application/zstd`, `unpack` `["zstd"]`, `region` `null`, com a chave própria `conformance_version`; o bloco
  `compatibility.sabia` ganha `conformance_version` e `conformance_spec`. É da mesma geração e do mesmo
  `format_version` dos bancos (o gerador não lista outro). O catálogo antigo também o traz numa chave de topo,
  `conformance` (`file`, `bytes`, `sha256`, `bytes_unpacked`, `conformance_version` e a contagem de casos em
  `cases`). Gerações anteriores ao conjunto não o têm.

<a id="pardal"></a>

### Pardal

- **`build_id`:** `AAAA-MM-DD-xxxxxxxx`, a data do `built_at` (UTC) e os 8 primeiros dígitos do sha256 da lista
  ordenada `caminho  sha256` de todos os arquivos de dado da geração. O Pardal não tem um extrato único (como o
  OpenStreetMap dos outros) para dar o sufixo; o hash do conteúdo cumpre o mesmo papel: dados iguais, sufixo igual.
- **Arquivos:** por estado (`region` a UF) e para o Brasil (`region` `BR`, `kind` `national`): os CSV (`format`
  `csv`), os radares também em GeoJSON, KML e GPX (`geojson`, `kml`, `gpx`), o zip do estado (`pardal-<UF>.zip`,
  `format` `pardal-bundle`, `unpack` `["zip"]`: a pasta do estado com todos esses arquivos e o `LICENCA-DADOS.txt`) e
  o banco SQLite (`pardal-<UF>.sqlite.zst`, `format` `sqlite`, `unpack` `["zstd"]`); os dois zips do Brasil
  (`pardal-brasil.zip` e `pardal-brasil-radares.zip`); e os polígonos das UFs (`brasil/ufs.geojson`, `auxiliary`).
  O `id` de um arquivo do repositório é o caminho dele (`estados/GO/radares.csv`); o de um anexo, o nome
  (`pardal-GO.zip`). Cada arquivo de dado tem a chave `content` com o nome da entrada antiga que o descreve
  (`cameras`, `limits`, `limit_lines`...). Todos são `DETAILED`, menos os polígonos (`null`); nenhum tem `requires`.
- **URLs:** os anexos (zips e bancos) apontam para a release da geração (`dados-AAAA-MM-DD`). Os arquivos do
  repositório são sempre membros de um zip (`container`, `member`) e, quando a geração vai para o repositório (o
  commit semanal), têm também URL própria: o mesmo nome de etiqueta no `raw.githubusercontent.com`. Nas gerações que
  saem só na release, a `url` deles é a do zip. `limites_trechos.csv` existe só no zip. Os zips saem iguais byte a
  byte de uma montagem para outra (datas fixas dentro do zip): o `publish.py` põe no catálogo o sha256 deles antes de
  o `release.py` montá-los, e o `release.py` recusa criar a release se o que montou não for o que o catálogo diz, ou
  se a etiqueta já existir. No commit semanal a release sai mesmo com os dados iguais aos da anterior, para as URLs
  do catálogo do repositório terem para onde apontar.
- **`mix_generations`:** `true` (cada estado é independente).
- **`compatibility.pardal`:** `pack_schema` (a versão do formato dos CSVs), `sqlite_schema_version`,
  `sqlite_min_version` (3.22.0), `sqlite_spec` (o formato do banco, no commit da geração) e a ordem das coordenadas
  em cada formato (`coordinate_order`: CSV latitude primeiro; GeoJSON e WKT longitude primeiro).
- **`sources`:** as datas por fonte (`source_dates`) e, quando o build está à mão, os extratos regionais do
  OpenStreetMap da Geofabrik, com sha256.

## Histórico

| Versão | Data | O que mudou |
|---|---|---|
| 1 | 2026-11-11 | Primeira versão. |
