# Pardal em SQLite: um banco por estado

Além dos CSVs (que continuam iguais, byte a byte), cada estado sai também num banco **SQLite**, com os mesmos
registros de todos os arquivos do estado numa tabela só, um **id estável** entre gerações, um **índice espacial por
célula** e os campos de segurança (sentido, precisão, confiança, datas) que dão para tirar dos dados sem inventar
nada. É a decisão D-04 da especificação do navegador offline (ETD, §16): CSV mantido + SQLite por UF com esquema
versionado e id estável.

- **Onde baixar:** só na release, como anexo próprio: `pardal-<UF>.sqlite.zst`
  (`https://github.com/Murkiriel/pardal/releases/latest/download/pardal-SP.sqlite.zst`). Não fica no repositório: o
  banco muda inteiro a cada geração e o commit semanal incharia o histórico.
- **Compactação:** zstd nível 19, com o tamanho original e o checksum no quadro. Descompacte uma vez, na instalação, e
  abra o `.sqlite` no lugar, só leitura. É o mesmo formato do Sabiá (`sabia-<UF>.sqlite.zst`), que o app já instala
  com o zstd-jni.
- **Piso técnico (o do Sabiá):** só o que o SQLite do Android 10 (3.22) tem: sem FTS5, sem R-Tree, sem colunas
  geradas; arquivo em modo rollback (journal `DELETE`, não WAL); índice comum (B-tree) por célula do zoom 13.
  Conferido em cada geração (`integrity_check`, esquema, modo do arquivo) e aberto no SQLite 3.22.0 na prova com os
  dados de 08/11/2026.
- **No catálogo:** a entrada `sqlite` de cada estado no `catalogo.json` (abaixo). Quem não conhece a chave a ignora.

## Catálogo

Cada estado do `catalogo.json` ganha a chave `sqlite` (nenhuma outra chave muda):

```json
"sqlite": {
  "release_asset": "pardal-GO.sqlite.zst",
  "bytes": 4416577,
  "sha256": "<sha256 do .zst>",
  "uncompressed_bytes": 18620416,
  "uncompressed_sha256": "<sha256 do .sqlite>",
  "schema_version": 1,
  "count": 163443,
  "counts": {"CAMERA": 1520, "SPEED_LIMIT": 125525, "SPEED_LIMIT_LINE": 29804, "STRUCTURE": 4956, "BUMP": 937,
             "HAZARD": 487, "TOLL": 36, "PORTABLE_RADAR_ZONE": 128, "POTHOLE_ZONE": 22, "MOTO_ACCIDENT_ZONE": 28,
             "ENFORCEMENT_CAMERA": 0}
}
```

| Chave | O que é |
|---|---|
| `release_asset` | O nome do anexo na release da mesma geração (e em `releases/latest/download/`) |
| `bytes`, `sha256` | Do arquivo compactado, o que se baixa: confira antes de descompactar |
| `uncompressed_bytes`, `uncompressed_sha256` | Do banco descompactado: o espaço que ele ocupa e a conferência depois de abrir |
| `schema_version` | A versão do esquema, a mesma de `meta.schema_version` |
| `count`, `counts` | Registros no banco, no total e por tipo: são as mesmas contagens dos CSVs da geração |

Recuse um `schema_version` maior que o que o app conhece. A versão sobe quando muda algo que um leitor antigo não
entenderia (tabela ou coluna renomeada ou removida, valor que muda de significado, a regra do id); tabela ou coluna
nova não sobe a versão.

## Esquema (`schema_version` 1)

| Tabela | O que é |
|---|---|
| `meta` | `key`, `value`: `schema_version`, `uf`, `built_at` (a geração), `crs` (`EPSG:4326`), `coord_scale` (`100000`), `cell_zoom` (`13`), `attribution` |
| `event` | Um registro por linha dos CSVs do estado (tabela abaixo) |
| `event_cell` | `cell`, `seq`: as células do zoom 13 de cada registro; a chave `(cell, seq)` é o índice espacial |

`PRAGMA user_version` também traz a versão do esquema.

### Coordenadas

Uma ordem só: **lat e lng em colunas separadas**, WGS84 (EPSG:4326), inteiros em **graus × 100.000** (5 casas, ~1 m),
como no Sabiá. `-16.68690` vira `-1668690`. Os pontos dos CSVs têm 6 casas: no banco ficam com 5 (diferença de até
0,55 m). As linhas (trechos) vão em `coords`: int32 little-endian `lat, lng, lat, lng...` (× 100.000), na ordem da
linha, o mesmo formato do `street_line.coords` do Sabiá. Não precisa de biblioteca de WKT:

```kotlin
fun decodeLine(blob: ByteArray): List<Pair<Double, Double>> {
    val b = java.nio.ByteBuffer.wrap(blob).order(java.nio.ByteOrder.LITTLE_ENDIAN)
    return List(blob.size / 8) { b.int / 1e5 to b.int / 1e5 }   // (lat, lng)
}
```

### `event`

| Coluna | Tipo | O que é |
|---|---|---|
| `seq` | INTEGER PK | A posição do registro **neste arquivo** (em ordem de célula, tipo e id): muda a cada geração. Serve só para ligar com `event_cell` |
| `id` | INTEGER | O **id estável** (regra abaixo): igual entre gerações enquanto o objeto não muda. Único no arquivo |
| `type` | TEXT | O tipo do registro e o CSV de onde ele vem (tabela abaixo) |
| `kind` | TEXT | O subtipo, como no CSV: `FIXED`/`SECTION`/`RED_LIGHT` (radar), `BRIDGE`/`TUNNEL`, `BUMP`..., `PLAZA`/`FREE_FLOW`, `BUS_LANE`...; nos buracos, o nível (`BAD`/`VERY_BAD`). Nulo nos tipos sem subtipo |
| `lat`, `lng` | INTEGER | O ponto (× 100.000). Nos trechos, o primeiro vértice da linha; na ponte/túnel, a primeira ponta |
| `end_lat`, `end_lng` | INTEGER | O fim do radar de trecho (`SECTION`) e a outra ponta da ponte/túnel; nulo no resto |
| `coords` | BLOB | A linha inteira dos trechos (`SPEED_LIMIT_LINE`, `PORTABLE_RADAR_ZONE`, `POTHOLE_ZONE`, `MOTO_ACCIDENT_ZONE`); nulo nos pontos |
| `source` | TEXT | A fonte, como no CSV (`DNIT+OSM`, `OSM:class`...). Nos tipos cujo CSV não tem a coluna: `OSM` (estruturas, lombadas, pontos de atenção), `PRF` ou `SIE-SC` (radar portátil: SC-xxx é da SIE-SC), `DNIT` (buracos), `PRF` (acidentes) |
| `source_id` | TEXT | O id do registro na fonte que o publicou, sem conversão, quando o leitor da fonte o tem (abaixo); nulo nos outros |
| `source_id_from` | TEXT | A fonte dona do `source_id` (uma das partes de `source`) |
| `active` | INTEGER | `1`/`0` como no CSV (radares e câmeras); `1` nos tipos sem a coluna (só entram os vigentes). **Não avise com `active = 0`** |
| `limit_kmh` | INTEGER | Limite (radar, limite, trecho de limite) |
| `limit_low_kmh` | INTEGER | Estimativa pelo lado baixo da faixa legal (só nos limites estimados) |
| `estimated` | INTEGER | `1` limite estimado (não sinalizado), `0` sinalizado ou oficial; nulo fora dos limites |
| `direction_deg` | INTEGER | Rumo do trânsito a que o registro se aplica, 0-359, como no CSV |
| `direction_scope` | TEXT | `ONE`, `BOTH` ou `UNKNOWN` (regra abaixo) |
| `position_accuracy_m` | INTEGER | Erro de posição esperado, em metros, só onde há medida (regra abaixo); nulo no resto |
| `confidence` | TEXT | `HIGH`, `MEDIUM` ou `LOW` (regra abaixo) |
| `observed_at` | TEXT | Data do dado (regra abaixo): `AAAA-MM-DD`, ou `AAAA-MM` quando a fonte só dá o mês; nulo sem data |
| `valid_from` | TEXT | Início da validade: a da lista vigente da PRF nos trechos do radar portátil; nulo no resto |
| `valid_until` | TEXT | Fim da validade: nenhuma fonte publicada traz hoje (sempre nulo; a coluna fica para quando trouxer) |
| `name` | TEXT | Nome da praça de pedágio |
| `road`, `km_from`, `km_to` | TEXT, REAL, REAL | Rodovia e km dos trechos (radar portátil, buracos, acidentes) |
| `km_direction` | TEXT | Buracos: o sentido do km avaliado, `INCREASING` ou `DECREASING` |
| `highway`, `oneway` | TEXT, INTEGER | Trechos de limite: classe da via no OSM e mão única (`1`/`0`; nulo se a fonte não diz) |
| `accidents`, `rider_deaths`, `period` | INTEGER, INTEGER, TEXT | Acidentes com moto: acidentes, motociclistas mortos e a janela `AAAA-MM/AAAA-MM` |
| `speed_fines_12m` | INTEGER | Radar portátil: multas de velocidade da PRF no trecho em 12 meses; nulo quando a fonte faltou |

| `type` | CSV com os mesmos registros |
|---|---|
| `CAMERA` | `radares.csv` |
| `SPEED_LIMIT` | `limites.csv` |
| `SPEED_LIMIT_LINE` | `limites_trechos.csv` (o do zip da release) |
| `STRUCTURE` | `estruturas.csv` |
| `BUMP` | `lombadas.csv` |
| `HAZARD` | `pontos_atencao.csv` |
| `TOLL` | `pedagios.csv` |
| `PORTABLE_RADAR_ZONE` | `radar_portatil.csv` |
| `POTHOLE_ZONE` | `buracos.csv` |
| `MOTO_ACCIDENT_ZONE` | `acidentes_moto.csv` |
| `ENFORCEMENT_CAMERA` | `cameras_fiscalizacao.csv` |

A geração confere, para cada estado, que o número de registros de cada tipo é o número de linhas do CSV
correspondente da mesma geração; se não for, o estado sai sem o banco e a publicação para (`failures`).

## Id estável

`id` = os 63 bits mais altos do **sha256** da chave do registro, com as partes unidas pelo caractere U+001F (inteiro
positivo, cabe num `Long`). A chave:

| Tipo | Com id da fonte (`source_id`) | Sem id da fonte |
|---|---|---|
| `CAMERA` | `CAMERA`, fonte dona, `id`, `source_id` | `CAMERA`, primeira parte de `source`, `pos`, `lat`, `lng` |
| `ENFORCEMENT_CAMERA` | ... `id`, `source_id`, `kind` | `ENFORCEMENT_CAMERA`, `source`, `pos`, `lat`, `lng`, `kind` |
| `STRUCTURE` | `STRUCTURE`, `OSM`, `id`, `way/...` | `STRUCTURE`, `OSM`, `pos`, `lat`, `lng`, `end_lat`, `end_lng` |
| `BUMP`, `HAZARD`, `TOLL` | tipo, fonte, `id`, `source_id` | tipo, `source`, `pos`, `lat`, `lng` |
| `SPEED_LIMIT` | — | `SPEED_LIMIT`, `source`, `pos`, `lat`, `lng`, `direction_deg` (vazio se nulo) |
| `SPEED_LIMIT_LINE` | — | `SPEED_LIMIT_LINE`, `source`, `line`, `direction_deg`, sha256 hex de `"lat,lng;lat,lng;..."` |
| `PORTABLE_RADAR_ZONE` | — | `PORTABLE_RADAR_ZONE`, `source`, `km`, `road`, `km_from`, `km_to` (1 casa) |
| `POTHOLE_ZONE` | — | `POTHOLE_ZONE`, `DNIT`, `km`, `road`, `km_direction`, `km_from`, `km_to` |
| `MOTO_ACCIDENT_ZONE` | — | `MOTO_ACCIDENT_ZONE`, `PRF`, `km`, `road`, `km_from`, `km_to` |

`lat`, `lng` são os inteiros gravados no banco (× 100.000), em texto. Exemplo: o radar do DNIT em `-16.0, -49.0`
tem a chave `CAMERA␟DNIT␟pos␟-1600000␟-4900000`. Dois registros com a mesma chave (o mesmo trecho cortado em dois
pedaços com os mesmos km): o primeiro na ordem do conteúdo fica com a chave e os outros ganham `#2`, `#3`... no fim.
Duas chaves diferentes com o mesmo id (improvável com 63 bits) são falha: o estado sai sem o banco e a publicação
para.

O que **não** está na chave e pode mudar sem trocar o id: o limite, a situação (`active`), o sentido do radar, a fonte
que confirma (`DNIT` → `DNIT+OSM` → `DNIT+OSM+INMETRO`: só a primeira parte conta), o nível do buraco, as contagens de
acidentes e multas, o mês do levantamento, as datas.

**Limitações:**

- Sem id da fonte, a posição é a identidade: um radar que a fonte move 2 m ganha id novo (e o antigo some). Mesmo um
  movimento menor que 1 m troca o id se cruzar a casa do arredondamento.
- O trecho de limite é identificado pela geometria: qualquer edição da via no OSM, ou a junção com um trecho vizinho,
  dá id novo. O valor do limite não está na chave.
- Os trechos por km mudam de id se os km mudam; o pedaço `#2` de um trecho repetido pode trocar de lugar com o
  primeiro se o conteúdo deles mudar.
- A primeira parte de `source` é a da chave: se uma mescla passar a pôr outra fonte na frente (um radar do OSM
  absorvido por um oficial novo, dois órgãos que passam a se juntar), o id muda. O radar do OSM absorvido some e o
  oficial fica com o id dele.
- O `source_id` só vem das leituras feitas pelo build. A geração em que uma fonte cai na edição publicada (os CSVs,
  sem id da fonte) troca, naquela geração, os ids dela pelos de posição; a primeira geração depois desta mudança também,
  para as fontes cuja cópia guardada é anterior a ela.
- O banco feito dos CSVs publicados (`datakit.build_sqlite --states`) não tem `source_id`: para os registros que o
  têm no build, os ids dos dois caminhos são diferentes. Não misture os dois numa comparação entre gerações.
- O id do OSM (`node/123`, `way/45`) muda quando o mapeador apaga o elemento e desenha outro.
- Não há índice em `id` (custaria ~8 bytes por registro, aleatórios, que não se compactam): `WHERE id = ?` varre a
  tabela. Se o app precisar, crie o índice depois de instalar.

### O que já vem com `source_id`

| Fonte | `source_id` |
|---|---|
| OpenStreetMap: radares, lombadas, pontos de atenção, pedágios, pontes e túneis | `node/<id>` ou `way/<id>` (o nó de alerta da relação `enforcement`, para o radar que só existe na relação) |
| CET-SP: radares e câmeras sem velocidade | o "CÓDIGO LOCAL" |
| DER-SE | o código do equipamento (`SE001R`, `SE348L`) |
| Detran-MA | o código do equipamento (`MA301R`) |

Nulo nas outras fontes. Para a maioria, o leitor não tem um código de equipamento confiável: DNIT, ANTT, DER-SP, DER-GO,
DER-MG, DER-PE, Rio, BH, Detran-DF, Fortaleza, Recife, João Pessoa, Curitiba, EPTC, Transalvador, SEMTRAN-PVH, AGETO-TO,
SEINFRA-BA, PRF (concessões) e Inmetro. Nos limites (pontos e trechos), nos trechos da PRF e do DNIT e nos pedágios da
ANTT a fonte não dá um id por registro (o ponto de limite é amostrado da via; o trecho é BR + km).

## Sentido, precisão, confiança e datas

**`direction_scope`:**

- `ONE` quando há `direction_deg`;
- `BOTH` nos limites (pontos e trechos) sem `direction_deg`: o CSV diz que o limite sem sentido vale para os dois
  sentidos (`maxspeed` sem `:forward`/`:backward` no OSM, trecho oficial sem sentido);
- `ONE` sem `direction_deg` nos buracos: o levantamento do DNIT é por sentido (`km_direction`) e a linha vem desenhada
  no sentido do trânsito; use o rumo do segmento da linha;
- `UNKNOWN` no resto. No radar, o `direction_deg` vazio mistura "os dois sentidos" e "sentido desconhecido": não
  há como separar. Avise nos dois sentidos.

**`position_accuracy_m`** (só onde a posição veio de um método indireto cujo erro foi medido; `gerador/FONTES.md`):

| Registro | Valor | Base |
|---|---|---|
| Radar só do Inmetro (`source = INMETRO`) | 100 | Posição pelo endereço (CNEFE): mediana de 23 m, 89% a até 100 m, nas capitais com lista oficial |
| Radar do DER-MG sem outra fonte com coordenada (`DER-MG`, `DER-MG+INMETRO`) | 900 | Posto por rodovia + km; o método medido no SNV: mediana 226 m, p75 873 m |
| Trechos postos pelo km do SNV (radar portátil da PRF, buracos, acidentes com moto) | 900 | O mesmo SNV (as pontas do trecho, ao longo da via) |
| Radar portátil da SIE-SC (km entre marcos do OSM) | 200 | Marcos quilométricos do OSM: mediana 83 m, 25% acima de 200 m |
| Todo o resto (coordenada publicada pelo órgão ou mapeada no OSM) | nulo | Sem medida por registro |

**`confidence`:**

- `LOW`: valor estimado (`estimated = 1`), não sinalizado;
- `HIGH`: duas ou mais fontes independentes (`+` em `source`), ou uma fonte oficial sozinha (órgão, PRF, DNIT,
  ANTT...);
- `MEDIUM`: só o OSM (mapeamento colaborativo sem confirmação oficial: radares, limites sinalizados, lombadas,
  pontos de atenção, estruturas, pedágios do OSM), ou só o Inmetro (o medidor existe, mas a posição veio do endereço e
  cerca de 1 em 10 é um radar já conhecido posto longe).

**`observed_at`:** a data mais nova entre as fontes do registro que têm data. Para as fontes oficiais é o
`source_dates` do catálogo: o dia em que o Pardal leu a fonte com sucesso (a fonte listava o objeto nesse dia; numa
fonte que caiu na cópia guardada, a data da cópia). Para o OSM, a data do extrato da Geofabrik. Nos buracos, o mês do
levantamento do DNIT (`AAAA-MM`); nos acidentes, o último mês da janela (`AAAA-MM`). Nulo para o Inmetro (o catálogo
não guarda a data dele) e para o que não tem data conhecida; no banco feito dos CSVs publicados, nulo também no OSM.

**`valid_from` / `valid_until`:** `valid_from` só nos trechos do radar portátil (início da validade da lista da PRF).
Nenhuma fonte publicada dá fim de validade; a situação da aferição do Inmetro já vira `active`.

## Como consultar por proximidade

A célula é o tile do zoom 13 (~4 a 5 km de lado no Brasil) como um número, a mesma conta do Sabiá:

```kotlin
fun cell(lat: Double, lng: Double): Long {
    val n = 8192
    val x = ((lng + 180.0) / 360.0 * n).toInt().coerceIn(0, n - 1)
    val latRad = Math.toRadians(lat.coerceIn(-85.05112878, 85.05112878))
    val y = ((1.0 - kotlin.math.asinh(kotlin.math.tan(latRad)) / Math.PI) / 2.0 * n).toInt().coerceIn(0, n - 1)
    return x.toLong() * n + y
}

fun neighborhood(lat: Double, lng: Double): List<Long> {
    val c = cell(lat, lng); val x = c / 8192; val y = c % 8192
    return (-1..1).flatMap { dx -> (-1..1).map { dy -> (x + dx) * 8192 + (y + dy) } }
}
```

Os 9 quadrados em volta da posição cobrem pelo menos uma célula inteira (~4 km) em toda direção. Cada registro está em
todas as células por onde passa (o ponto; as duas pontas do radar de trecho; a linha inteira dos trechos, da ponte e
do túnel), então um trecho longo é achado de qualquer ponto ao longo dele:

```sql
SELECT id, type, kind, lat, lng, limit_kmh, direction_deg, direction_scope, confidence, position_accuracy_m
FROM event
WHERE seq IN (SELECT seq FROM event_cell WHERE cell IN (?, ?, ?, ?, ?, ?, ?, ?, ?))
  AND type = 'CAMERA' AND active = 1
```

Depois, no app, a distância exata (e a distância até cada segmento de `coords`, nos trechos), o sentido e o resto da
regra de alerta. Os registros vão no arquivo em ordem de célula: uma consulta lê páginas vizinhas.

Medido nos bancos da edição de 08/11/2026 (num PC com Linux, cache quente): perto da Av. Paulista (SP), os 9
quadrados têm 24.058 registros, 500 deles radares ativos; a consulta dos radares ativos leva ~6 ms no SQLite 3.22.0,
e trazer todos os 24.058 registros, ~26 ms no SQLite 3.45.

## Tamanhos (edição de 08/11/2026)

27 estados: 444 MB de bancos, 105 MB compactados. O maior, SP: 686.120 registros, 78,4 MB (18,2 MB compactado); o
menor, AP: 6.010 registros, 0,7 MB (0,2 MB). A maior parte é limite: em SP, 461.290 pontos e 159.701 trechos.

## Como é gerado

`gerador/datakit/build_sqlite.py`. No build, das mesmas listas que viram os CSVs do pacote (`build_pack.py`, com o
`source_id`); o `build_catalog.py` confere o banco contra os CSVs da geração, compacta e escreve a entrada do
catálogo; o `scripts/release.py` o anexa à release. A partir dos CSVs já publicados (sem as fontes brutas e sem
`source_id`):

```
cd gerador
python run.py datakit.build_sqlite --states ../estados --catalog ../catalogo.json \
    --lines <pasta com <UF>/limites_trechos.csv, extraídos dos zips da release> --out <pasta>
```
