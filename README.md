# Pardal — radares e limites de velocidade do Brasil

**Lista de radares do Brasil** (fixos, lombadas eletrônicas, radares de trecho e avanço de
sinal) e **limites de velocidade das vias**, com localização (latitude e longitude), em
arquivos para baixar e usar offline: **CSV**, **GeoJSON**, **KML** (Google Earth) e **GPX**
(GPS e apps de navegação), e um banco **SQLite** por estado na release. Um conjunto do Brasil inteiro e um
por estado.

"Pardal" é o apelido popular do radar fixo. O conjunto junta, num formato só, o que DNIT,
ANTT, Inmetro, DERs estaduais e prefeituras publicam em dezenas de lugares diferentes, mais
o que a comunidade do OpenStreetMap mapeia.

> **Aviso.** Não é fonte oficial e nenhum órgão endossa este trabalho. Os dados podem
> estar desatualizados ou errados. A sinalização da via sempre prevalece.

**Brasil inteiro:** [`radares.csv`](brasil/radares.csv) · [`radares.gpx`](brasil/radares.gpx) ·
[`radares.kml`](brasil/radares.kml) · [`radares.geojson`](brasil/radares.geojson) ·
[`limites.csv`](brasil/limites.csv) · [`limites_estimados.csv`](brasil/limites_estimados.csv) ·
[`estruturas.csv`](brasil/estruturas.csv) · [`ufs.geojson`](brasil/ufs.geojson) (contorno dos estados)
**Por estado:** pasta [`estados/`](estados), por exemplo [`estados/SP/`](estados/SP).
**Índice:** [`catalogo.json`](catalogo.json) · **Versão do dia:** [release mais recente](https://github.com/Murkiriel/pardal/releases/latest)

## Situação

Em 2026-11-11:

| Item | Como está |
|---|---|
| Release mais recente | `dados-2026-11-10`, com dados de 2026-11-10 (20.809 radares no Brasil). O link `releases/latest/download/` aponta sempre para a mais nova |
| Arquivos do repositório | Os do commit semanal de 2026-11-08 (`built_at` do [`catalogo.json`](catalogo.json)); o próximo sai a partir do domingo, 2026-11-15 |
| Banco SQLite por estado | Entra a partir da próxima release: o código foi para o `main` em 2026-11-11, e as releases até `dados-2026-11-10` ainda não têm o `pardal-<UF>.sqlite.zst` |
| Geração | A agendada de 2026-11-11 falhou; a [issue](https://github.com/Murkiriel/pardal/issues) "Geração falhando" fica aberta até a próxima passar, e a release anterior continua no ar |
| Cadência | Geração todo dia, com release quando algum dado muda; commit no repositório uma vez por semana; releases guardadas por 90 dias, menos as semanais ([Geração e reprodutibilidade](#geração-e-reprodutibilidade)) |
| Formato | CSV, GeoJSON, KML e GPX; SQLite (`schema_version` 1) na release; catálogo no `schema` 2 |

## Baixar e usar

Os arquivos estão em dois lugares, no mesmo formato:

- **no repositório** (`brasil/`, `estados/`, `catalogo.json`), atualizado uma vez por semana: bom para baixar um
  arquivo solto pelo navegador ou acompanhar o histórico;
- **na release mais recente**, gerada todo dia em que algum dado muda: `pardal-<UF>.zip` (todos os arquivos do
  estado, inclusive o `limites_trechos.csv`), `pardal-<UF>.sqlite.zst` (o estado num banco SQLite, a partir da
  próxima release), `pardal-brasil.zip`, `pardal-brasil-radares.zip`, `catalogo.json` e `SHA256SUMS.txt`. O link
  `https://github.com/Murkiriel/pardal/releases/latest/download/pardal-<UF>.zip` traz sempre a mais nova.

Num app: leia o `catalogo.json`, baixe só os estados de que precisa, confira o `sha256` de cada arquivo e só então
troque o que o aparelho já tem (ver "Para quem faz app de alerta").

### O que tem no repositório

```
brasil/                 o país inteiro
  radares.csv           todos os radares
  radares.gpx           radares ativos, para GPS e apps de navegação
  radares.kml           radares ativos, para Google Earth
  radares.geojson       todos os radares, para mapas web e QGIS
  limites.csv           pontos de limite de velocidade sinalizados
  limites_estimados.csv limites estimados pelo tipo de via (.csv.gz se passar de 95 MB)
  estruturas.csv        pontes, viadutos e túneis
  ufs.geojson           contorno simplificado de cada estado, para escolher o pacote pela posição
estados/<UF>/           um estado (AC, AL, AM … SP, TO)
  radares.csv  radares.gpx  radares.kml  radares.geojson
  limites.csv           limites sinalizados e estimados (coluna `estimated`), em pontos
  (limites_trechos.csv  os mesmos limites como trechos de via: só no zip do estado na release, ver abaixo)
  estruturas.csv
  lombadas.csv          lombadas, quebra-molas, faixas elevadas e sonorizadores
  pontos_atencao.csv    passagens de nível, curvas e cruzamentos perigosos, travessia de animais,
                        áreas escolares, queda de barreira e painéis de velocidade
  pedagios.csv          praças de pedágio e pórticos de free flow
  radar_portatil.csv    trechos de rodovia federal aptos à fiscalização com radar portátil (PRF)
  buracos.csv           trechos de rodovia federal com buracos (panela ruim ou péssima no ICM do DNIT)
  acidentes_moto.csv    trechos de rodovia federal com muitos acidentes com moto (PRF)
  cameras_fiscalizacao.csv  câmeras que fiscalizam outra infração que não velocidade (faixa exclusiva,
                        conversão proibida, rodízio, parada sobre a faixa...)
                        (fora radares e limites, o arquivo que ficaria vazio no estado não sai e não
                        entra no catálogo: cameras_fiscalizacao.csv só existe em SP, MG e PR)
catalogo.json           índice dos pacotes por estado: arquivos, tamanho, sha256,
                        contagens e data de geração
docs/CATALOGO.md        contrato de catálogo comum aos quatro geradores (chave contract); o Pardal na seção #pardal
scripts/to_geojson.py converte qualquer CSV acima para GeoJSON (ver abaixo)
gerador/                código que baixa as fontes e gera todos os arquivos acima
```

Limites e estruturas são publicados só em CSV (os limites do Brasil com os estimados num
arquivo à parte, para caber no limite de 100 MB por arquivo do GitHub). Para ter qualquer um
deles em GeoJSON, use o `scripts/to_geojson.py`.
Limites não saem em GPX nem KML: aparelhos de GPS usam esses formatos para pontos de
interesse, e o limite é um valor da via, não um lugar.

### Converter para GeoJSON

O `scripts/to_geojson.py` converte qualquer CSV do Pardal (radares, limites, limites estimados,
estruturas, inclusive `.csv.gz`) para GeoJSON. Só precisa de Python 3.8 ou mais novo, sem
instalar nada:

```
python scripts/to_geojson.py estados/GO/limites.csv                   # gera estados/GO/limites.geojson
python scripts/to_geojson.py estados/GO/limites.csv --no-estimated   # só os limites sinalizados
python scripts/to_geojson.py brasil/limites_estimados.csv -o estimados.geojson
```

Pontos viram `Point`, estruturas viram `LineString` e as demais colunas viram propriedades
(`active` e `estimated` como verdadeiro/falso). Arquivos grandes são convertidos sem
carregar tudo na memória (o Brasil inteiro, 1,4 milhão de pontos, leva cerca de 10 s).

## Formato

> **Ordem das coordenadas: muda conforme o formato.** Todas estão em **WGS84** (EPSG:4326), em graus
> decimais; os dados oficiais em SIRGAS 2000 entram sem conversão (a diferença para o WGS84 fica abaixo
> de 1 m).
>
> | Formato | Ordem | Exemplo |
> |---|---|---|
> | **CSV** (colunas) | **`lat,lng`** (estruturas: `lat1,lng1,lat2,lng2`) | `-16.680000,-49.250000` |
> | **GeoJSON** (`radares.geojson`, `ufs.geojson`, saída do `to_geojson.py`) | **`[lng, lat]`**, como manda o padrão (RFC 7946), inclusive o `end` dos radares de trecho | `[-49.25, -16.68]` |
> | **WKT** (coluna `wkt` dos CSVs de trechos) | **`lng lat`** (x y), pontos separados por vírgula | `LINESTRING(-49.25000 -16.68000, -49.24800 -16.68100)` |
> | KML | `lng,lat,altitude`, como manda o padrão | `<coordinates>-49.25,-16.68,0</coordinates>` |
> | GPX | atributos `lat` e `lon` | `<wpt lat="-16.68" lon="-49.25">` |
>
> Num mesmo pacote há as duas ordens: o `radares.csv` traz `lat,lng` e o `limites_trechos.csv`, no WKT,
> `lng lat`. Trocar a ordem põe o ponto em outro lugar do planeta sem dar erro.

**Radares (CSV):** `lat,lng,kind,limit_kmh,source,active,end_lat,end_lng,direction_deg`

| Coluna | Significado |
|---|---|
| `kind` | `FIXED` (radar de velocidade ou lombada eletrônica), `SECTION` (radar de trecho, com o fim em `end_lat,end_lng`), `RED_LIGHT` (avanço de sinal) |
| `limit_kmh` | Limite fiscalizado, quando a fonte informa (veículo leve) |
| `source` | De onde veio o ponto (`OSM`, `DNIT`, `ANTT`, `DER-SP`, `RIO`, `INMETRO`, `PRF`…). Quando mais de uma fonte traz o mesmo radar, elas vêm juntas com `+` (ex.: `DNIT+OSM`, confirmado por duas fontes independentes). `INMETRO` sozinho é um radar que só o cadastro de aferições do Inmetro conhece, com a posição tirada do endereço (ver as perguntas frequentes) |
| `active` | `0` quando o radar está desativado ou com a aferição do Inmetro vencida |
| `direction_deg` | Sentido fiscalizado: rumo do trânsito que o radar fiscaliza, inteiro de 0 a 359 em graus a partir do norte (0 = norte, 90 = leste, 180 = sul, 270 = oeste). **Vazio não quer dizer "os dois sentidos"**: ver "Sentido do radar" abaixo |

No GPX e no KML entram só os radares ativos, com o nome no formato "Radar 60 km/h" e o
sentido na descrição ("sentido 92° (leste)"). O GeoJSON tem todos, com as mesmas informações nas
propriedades (`direction_deg` vazio vira `null`).

**Sentido do radar (`direction_deg`).** O que o arquivo traz é só o rumo do trânsito fiscalizado; não
traz uma margem de tolerância. O sentido vem das fontes oficiais que o informam ("crescente/decrescente"
do km no DNIT, na ANTT, na planilha das concessões da PRF e no DER-GO, Norte/Sul/Leste/Oeste na
Artesp, faixas por sentido no DER-SP, centro/bairro na CET de São Paulo), convertido em rumo pela
geometria da via no ponto do radar (SNV do DNIT, malha estadual da Goinfra e OpenStreetMap). A tag `direction` dos radares do OpenStreetMap não é
usada: medida contra as fontes oficiais, ela aponta o sentido contrário na maioria das rodovias (muitos
mapeadores marcam para onde a câmera olha). Na geração de 2026-11-08, 17,9% dos radares têm o campo
preenchido.

- **Vazio mistura dois casos que hoje não dá para separar:** o radar vale para os dois sentidos (a fonte
  diz isso, ou duas fontes trazem o mesmo radar em sentidos opostos) **ou** o sentido é desconhecido (a
  fonte não informa, ou informa mas o rumo não pôde ser calculado). Trate vazio como "pode valer para os
  dois sentidos" e avise nos dois.
- **90° é a regra do gerador, não a do app.** Ao juntar fontes, o gerador considera opostos dois
  sentidos que diferem em mais de 90°: duas fontes com o radar no mesmo ponto e sentidos opostos viram
  um radar sem sentido (os dois), e dois radares próximos (o do OpenStreetMap e o oficial, ou os de dois
  órgãos) só viram um se os sentidos conhecidos diferirem em até 90°.
- **No app, a recomendação é 60°** (ver "Para quem faz app de alerta"): com o campo preenchido, ignore o
  radar só se o rumo do veículo diferir dele em mais de 60°, e só com GPS preciso e em movimento. É
  uma sugestão, não uma propriedade do dado; a margem é mais estreita que os 90° porque, perto de 90°,
  o veículo está atravessando a via do radar, não seguindo por ela.

**Limites (CSV):** `lat,lng,limit_kmh,source,estimated,limit_low_kmh,direction_deg`. Cada ponto
marca o limite naquele lugar da via; o valor vale até o próximo ponto. Onde há dado oficial
(placas das concessões federais, velocidade regulamentada das ruas do Rio de Janeiro e de São
Paulo), ele substitui o do OpenStreetMap naquele trecho.

| Coluna | Significado |
|---|---|
| `source` | `ANTT`, `RIO`, `CET-SP`, `OSM` (valor sinalizado no mapa), `OSM:zone` ou `OSM:class` (estimados) |
| `estimated` | `1` quando o valor **não é sinalizado**: foi estimado pela regra do Código de Trânsito para aquele tipo de via (rodovia, avenida, via local), porque a via não tem limite cadastrado. `0` para valor sinalizado ou oficial |
| `limit_low_kmh` | Só nos estimados: a mesma estimativa pelo lado baixo da faixa legal, para quem prefere errar para o lado cauteloso (ex.: 80 onde o típico é 100) |
| `direction_deg` | Preenchido quando a placa vale só para um sentido (rumo do trânsito em graus, como nos radares). Nas rodovias concedidas em que cada sentido tem um limite diferente, e nas vias do OpenStreetMap marcadas com um limite por sentido (`maxspeed:forward`/`maxspeed:backward`), há um ponto para cada sentido no mesmo lugar. Vazio = vale para os dois sentidos |

Os estimados cobrem só a rede principal (autoestradas, troncos, primárias, secundárias e
terciárias). Estradas rurais sem classificação e ruas de bairro ficam sem estimativa.

**Limites como trechos (CSV, só por estado):** `limit_kmh,source,estimated,limit_low_kmh,direction_deg,highway,oneway,wkt`.
Os mesmos limites do `limites.csv`, mas como a via: cada linha é um trecho (`wkt` = `LINESTRING(lng lat, ...)`, WGS84, cinco
casas, ~1 m) com o limite que vale ao longo dele, para o app encaixar a posição na via mais perto em vez de adivinhar a via
por um ponto (que erra em rua paralela, cruzamento, viaduto e marginal). O `limites.csv` continua igual.

| Coluna | Significado |
|---|---|
| `limit_kmh` | Limite do trecho |
| `source` | Como em `limites.csv`: `ANTT`, `RIO`, `CET-SP`, `OSM`, `OSM:zone` ou `OSM:class` |
| `estimated` | `1` quando o valor foi estimado pelo tipo da via (não é sinalizado), como em `limites.csv`; `limit_low_kmh` é a estimativa do lado baixo |
| `direction_deg` | Preenchido quando o limite vale só para um sentido (placa de um lado, `maxspeed:forward`/`backward` diferentes): rumo médio do trânsito, 0-359. Nesses trechos a linha vem **desenhada no sentido do trânsito**; para casar, use o rumo do segmento da linha mais perto da posição, não só este resumo. Vazio = vale para os dois sentidos |
| `highway` | Classe da via no OpenStreetMap (`motorway`, `primary`, `residential`...); vazia nas fontes oficiais que não a informam (`ANTT`, `RIO`, `CET-SP`). Serve para casar a via do app (ou do roteador) com o trecho e para escolher entre vias paralelas |
| `oneway` | `1` via de mão única (a linha segue o trânsito), `0` mão dupla (o sentido do desenho não quer dizer nada); vazio na fonte oficial que não informa |

Exemplo (uma avenida de mão dupla com 60 km/h sinalizado no OSM, e um sentido de uma via com 40 km/h estimado):

```
limit_kmh,source,estimated,limit_low_kmh,direction_deg,highway,oneway,wkt
60,OSM,0,,,primary,0,"LINESTRING(-49.25000 -16.68000, -49.24800 -16.68100)"
40,OSM:class,1,40,90,tertiary,0,"LINESTRING(-49.30000 -16.70000, -49.29500 -16.70000)"
```

As vias contíguas de mesmo limite, classe e sentido vêm juntas numa linha só (no máximo ~5 km); a geometria é simplificada
a 3 m (as curvas ficam, os vértices de reta saem). Onde há trecho oficial (placas da ANTT sobre a rota do SNV, ruas do Rio de
Janeiro, vias de trânsito rápido e arteriais de São Paulo), a linha do OpenStreetMap que ele cobre (a até 50 m, na mesma
orientação) não entra: se há duas linhas na mesma via, a oficial vale. Uma linha que cruza a divisa de dois estados vem nos
dois pacotes. Não há versão do Brasil inteiro (somados os estados, ~172 MB; o maior estado, Minas Gerais, tem ~31 MB).

**Onde baixar:** o `limites_trechos.csv` **não fica no repositório** (seriam ~172 MB mudando a cada geração). Ele vai só no zip de
cada estado da release (sai todo dia com dado novo): `https://github.com/Murkiriel/pardal/releases/latest/download/pardal-<UF>.zip`, dentro dele
`<UF>/limites_trechos.csv` (comprimido, SP cai de 29 MB para ~6 MB). No `catalogo.json`, a entrada `limit_lines` de cada estado
traz `release_asset` (o nome do zip), `asset_path` (o caminho dentro dele) e `bytes`, `sha256` e `count` do CSV
descompactado, para conferir depois de extrair (pacote no schema 10).

**Câmeras de fiscalização sem velocidade (CSV, só por estado):** `lat,lng,kind,source,active`. Locais oficiais de câmera que
fiscalizam **outra infração** que não excesso de velocidade nem avanço de sinal (esses são os radares do `radares.csv`):
um local com várias infrações vira uma linha por infração. `kind`: `BUS_LANE` (faixa exclusiva de ônibus), `NO_TURN`
(conversão proibida), `NO_U_TURN` (retorno proibido), `MANDATORY_TURN` (conversão obrigatória), `STOP_ON_CROSSWALK` (parada
sobre a faixa de pedestres), `ROAD_ROTATION` (rodízio), `TRUCK_RESTRICTION` (restrição de caminhão: zona, faixa ou peso),
`CHARTER_RESTRICTION` (zona de restrição de fretados), `MOTORCYCLE_RESTRICTION` (restrição a motocicletas) ou `OTHER`.
`source`: `CET-SP:CAM` (São Paulo), `BHTRANS:CAM` (Belo Horizonte) ou `CURITIBA:CAM`, um código próprio por fonte, nunca o
do radar do mesmo órgão. `active`: só entram locais em operação, então é sempre `1` (a coluna acompanha o `radares.csv`). O
mesmo local pode estar nos dois arquivos, no `radares.csv` por um tipo de infração e aqui por outro. Só São Paulo, Belo
Horizonte e Curitiba publicam esses locais com coordenada; para os demais estados o arquivo não existe. No `catalogo.json`,
a entrada `enforcement_cameras` (pacote no schema 11).

**Contornos dos estados (`brasil/ufs.geojson`):** `FeatureCollection` com uma feição por UF (`properties`: `uf`, `name`;
geometria `Polygon` ou `MultiPolygon`), a malha oficial do IBGE simplificada a 0,02° (~2 km; o desvio medido chega a ~3 km)
e com quatro casas decimais: ~130 KB. Serve para o app descobrir em que estado está e quais pacotes baixar, não para dizer se
um ponto está dentro da divisa. O `catalogo.json` aponta para ele na chave `ufs_geojson` (`file`, `bytes`, `sha256`).

**Estruturas (CSV):** `lat1,lng1,lat2,lng2,kind`, com `kind` = `BRIDGE` ou `TUNNEL`.

**Lombadas (CSV, só por estado):** `lat,lng,kind`, do OpenStreetMap (`traffic_calming`): o que faz o veículo
pular, não o que só estreita a via. `kind` = `BUMP` (lombada curta, quebra-molas), `HUMP` (lombada longa), `TABLE`
(faixa elevada), `CUSHION` (almofada, lombada com vãos), `RUMBLE_STRIP` (sonorizador) ou `UNSPECIFIED` (marcada sem
tipo). A faixa elevada desenhada como linha vira o ponto do meio. No `catalogo.json`, a entrada `bumps` de cada
estado que tem alguma (pacote no schema 3; quem lê o schema 2 ignora a chave).

**Pontos de atenção (CSV, só por estado):** `lat,lng,kind`, do OpenStreetMap. `kind` = `LEVEL_CROSSING` (passagem de
nível: a via cruza a linha férrea, `railway=level_crossing`), `CURVE` (curva perigosa), `DANGEROUS_JUNCTION`
(cruzamento perigoso), `ANIMAL_CROSSING` (travessia de animais), `SCHOOL_ZONE` (área escolar), `FALLING_ROCKS` (queda
de barreira), `SPEED_DISPLAY` (painel que mostra a velocidade, `highway=speed_display`) ou `HAZARD` (outro perigo
sinalizado no mapa, `hazard=*`: pista escorregadia, neblina, alagamento...). Um trecho desenhado como linha vira o ponto
do meio. Semáforos não entram (são dezenas de milhares e não pedem aviso). Na geração de 2026-11-08: 19.174 pontos no
Brasil, 17.391 deles passagens de nível; os perigos marcados com `hazard=*` ainda são poucos no OSM do Brasil (cerca de
1.800). No `catalogo.json`, a entrada `hazards` (pacote no schema 9).

**Pedágios (CSV, só por estado):** `lat,lng,kind,name,source`. As praças das rodovias federais concedidas vêm da ANTT
(com o nome da praça, só as ativas) e as demais do OpenStreetMap (`barrier=toll_booth`, `highway=toll_gantry`); o
mesmo pedágio nas duas fontes, a até 300 m, fica um só, com o nome da ANTT. `kind` = `PLAZA` (praça com cabine) ou
`FREE_FLOW` (pórtico eletrônico, sem parar). Sem preço: as tabelas de tarifa publicadas estão desatualizadas. No
`catalogo.json`, a entrada `tolls` (pacote no schema 4).

**Trechos aptos ao radar portátil (CSV, só por estado):** `road,km_from,km_to,valid_from,wkt,speed_fines_12m`. A relação que a PRF
publica (Res. Contran 798/2020, art. 7º): os trechos das rodovias federais onde a fiscalização de velocidade com
equipamento portátil **pode** acontecer, não a posição de um radar. `road` é a BR (`BR-060`), `km_from`/`km_to` o
trecho na quilometragem do SNV, `valid_from` o início da validade da lista vigente da PRF e `wkt` a linha da rodovia
entre os dois km (`LINESTRING(lng lat, ...)`, pelo SNV do DNIT; simplificada a 15 m). O trecho que atravessa duas linhas
do SNV vira um pedaço por linha; contornos e acessos ("BR-101 (Contorno viário)") ficam de fora (o km não é o da BR).
`speed_fines_12m` (desde o schema 7) são as multas de velocidade (art. 218 do CTB) que a PRF aplicou nos km do trecho
nos 12 meses mais novos dos dados abertos dela, só a contagem: diz onde a PRF de fato fiscaliza, não onde haverá radar;
vazio quando a fonte faltou na geração, `0` quando não houve multa. Em SC entram também os locais do radar portátil
nas rodovias estaduais que a SIE publica (`road` = `SC-401`...): cada local vira o trecho entre os dois marcos
quilométricos do OSM que o cercam, pelo caminho da rodovia, sem as multas. No `catalogo.json`, a entrada `portable_radar`
(pacote no schema 5).

**Trechos com buracos (CSV, só por estado):** `road,km_from,km_to,direction,level,month,wkt`. Do levantamento mensal
de condições do pavimento do DNIT (ICM), os km com **panela (buraco) ruim ou péssima**, juntados quando seguidos na mesma
rodovia e sentido. `direction` é o sentido avaliado (`INCREASING` ou `DECREASING` do km), `level` = `BAD` (ruim) ou
`VERY_BAD` (péssimo, o pior do trecho), `month` o mês do levantamento e `wkt` a linha da rodovia pelo SNV, desenhada no
sentido do tráfego. Só a malha do DNIT (as concessões não entram no levantamento). No `catalogo.json`, a entrada
`potholes` (pacote no schema 6).

**Trechos com muitos acidentes com moto (CSV, só por estado):** `road,km_from,km_to,accidents,rider_deaths,months,wkt`.
Dos dados abertos de acidentes da PRF (o corte por pessoa), os km de rodovia federal com 5 ou mais acidentes com
motocicleta, motoneta ou ciclomotor nos 12 meses mais novos publicados, juntados quando seguidos na mesma BR.
`accidents` é a soma desses acidentes no trecho, `rider_deaths` os motociclistas mortos neles, `months` a janela
(`AAAA-MM/AAAA-MM`) e `wkt` a linha da rodovia pelo SNV. Só contagens por lugar, sem data, hora nem pessoa. No
`catalogo.json`, a entrada `moto_accidents` (pacote no schema 8).

**Banco SQLite por estado (só na release, a partir da próxima):** `pardal-<UF>.sqlite.zst`, ao lado do zip de cada
estado na release. Os mesmos
registros de todos os arquivos do estado (inclusive os trechos de limite) numa tabela só, com id estável entre gerações, índice
por célula (zoom 13) para buscar por proximidade, os trechos sem WKT e, por registro, sentido (`direction_scope`), precisão,
confiança e data do dado. Abre no SQLite do Android 10 (3.22). No `catalogo.json`, a entrada `sqlite` de cada estado
(`release_asset`, `bytes`, `sha256`, `uncompressed_bytes`, `schema_version`). Os CSVs continuam iguais. Formato, regra do
id e limitações em [`docs/FORMATO_SQLITE.md`](docs/FORMATO_SQLITE.md).

**Catálogo (`catalogo.json`, `schema` 2):** `built_at` (a geração, em UTC), `source_dates` (a data do dado de cada
fonte), `ufs_geojson` (o contorno dos estados) e `ufs`, com uma entrada por UF e uma `BR` (o Brasil inteiro). Cada
entrada traz `name`, `bbox`, `built_at`, `coverage` (`level`: de que esfera vêm os radares, `federal`, `state` e
`municipal`, juntos com `+`; `sources`: as fontes), `counts` e, para cada arquivo, `file`, `bytes`, `sha256` e
`count`; os que só existem na release (`limit_lines`, `sqlite`) trazem `release_asset` no lugar de `file`. O `bbox` é
`[lat_min, lon_min, lat_max, lon_max]`, **latitude primeiro**, no WGS84, ao contrário do GeoJSON. É um retângulo
aproximado da UF: difere em até 0,07° do retângulo da malha do IBGE e deixa de fora as ilhas oceânicas de PE e do
ES. Serve para uma triagem; para saber em que estado fica um ponto, use o `ufs.geojson`.

Todos em UTF-8, coordenadas em graus decimais WGS84, na ordem de cada formato (ver o quadro no começo
desta seção: CSV `lat,lng`; GeoJSON `[lng, lat]`; WKT `lng lat`).

## Para quem faz app de alerta

Sugestões para usar os arquivos num aplicativo que avisa o motorista, tiradas do que funciona nos apps de alerta
que já existem:

- **Baixe por estado e confira.** O `catalogo.json` traz, por estado, cada arquivo com `bytes`, `sha256` e a data de
  geração (`built_at`). Baixe só quando o `sha256` mudar e confira o arquivo antes de trocar o que o aparelho já tem; assim
  o app funciona sem internet e não fica com um arquivo pela metade. Mostre ao usuário quando a base estiver velha.
- **Avise pela distância na rota, não por raio.** Com rota, projete os radares sobre ela antes de sair e avise o
  próximo à frente pela distância ao longo da rota (uns 500 m): o radar de uma rua paralela ou de um viaduto não
  dispara. Sem rota, use um raio pequeno e só os radares à frente do veículo.
- **Sentido.** Quando `direction_deg` vem preenchido, ignore o radar se o rumo do veículo diferir dele em mais de
  60°, mas só com o GPS preciso (precisão de 15 m ou melhor) e em movimento: parado ou com GPS ruim, o rumo não é
  confiável. Vazio = avisar nos dois sentidos (vazio pode ser "os dois sentidos" ou "sentido desconhecido"; ver
  "Sentido do radar").
- **Escolha os pacotes pela posição.** O `brasil/ufs.geojson` traz o contorno de cada estado (simplificado: erra até ~3 km
  na divisa). Ache o estado pelo ponto dentro do polígono; a menos de ~5 km de uma divisa, ou fora de todos os polígonos (mar,
  ponte), tenha também os pacotes vizinhos. Em vez de baixar o `brasil/` inteiro, baixe só o estado onde o usuário está e os
  vizinhos da rota.
- **Limite pela via, não pelo ponto.** O `limites_trechos.csv` do estado (no zip da release, entrada `limit_lines` do
  catálogo) traz o trecho da via com o limite: encaixe a posição
  (GPS) no trecho mais perto cuja direção combine com o rumo do veículo (diferença de até uns 30°, e, onde `direction_deg`
  vier preenchido, só o trecho do seu sentido: a linha vem desenhada no sentido do trânsito). Com mais de um trecho a poucos
  metros (vias paralelas, marginal, viaduto), prefira a fonte oficial (`ANTT`, `RIO`, `CET-SP`) ao `OSM`, o valor sinalizado
  (`estimated=0`) ao estimado (`estimated=1`), e mantenha o trecho em que você já estava enquanto ele ainda combinar (evita
  alternar de via a cada leitura do GPS). `highway` e `oneway` ajudam a desempatar quando o app sabe a classe da via. Onde
  não há trecho (estados sem arquivo, vias sem limite nem estimativa), use os pontos do `limites.csv` como antes.
- **Grupos de alerta que o usuário liga e desliga:** radar de velocidade (`FIXED`, `SECTION`), avanço de sinal
  (`RED_LIGHT`), perigos na via (lombadas, buracos, passagens de nível, curvas), pontos de atenção (pedágio, área
  escolar, travessia de animais, radar portátil) e câmeras de outras infrações (`cameras_fiscalizacao.csv`: faixa exclusiva,
  conversão proibida, rodízio; por `kind`).
- **Fale pouco.** Dois avisos por radar (longe e perto) bastam, e silêncio se o veículo já estiver abaixo do limite;
  `active = 0` não deve avisar.

## Perguntas frequentes

**Onde baixar a lista de radares do Brasil atualizada?** Na pasta `brasil/`: `radares.csv`
(planilha), `radares.gpx` (GPS) ou `radares.kml` (Google Earth). Para um estado só, use a
pasta dele, por exemplo `estados/MG/radares.csv`. O repositório é atualizado uma vez por semana;
a versão do dia está na release mais nova (`pardal-brasil-radares.zip`, ou `pardal-<UF>.zip` por
estado).

**Como colocar os radares no GPS ou no celular?** Importe o `radares.gpx` (do Brasil ou do
seu estado) como pontos favoritos ou de interesse: OsmAnd, Organic Maps, Garmin BaseCamp e
a maioria dos apps de navegação aceitam GPX. No Google Earth, importe o `radares.kml`. O
Google My Maps aceita até 2.000 pontos por camada, então use o KML de um estado.

**Tem o limite de velocidade de cada rua e rodovia?** Onde existe dado: placas oficiais nas
rodovias federais concedidas, velocidade regulamentada das ruas do Rio de Janeiro e de São
Paulo e o `maxspeed` do OpenStreetMap no resto, mais os estimados na rede principal. Está em
`estados/<UF>/limites.csv`.

**Como abrir os limites no QGIS ou num mapa web?** Converta para GeoJSON com
`python scripts/to_geojson.py estados/<UF>/limites.csv`, ou abra o CSV direto no QGIS como camada
de texto delimitado, com `lng` como X e `lat` como Y. Os trechos (`limites_trechos.csv`, do zip do estado na release) abrem no QGIS como texto
delimitado com "Definição de geometria" em WKT e a coluna `wkt` (o `to_geojson.py` só converte pontos e estruturas).

**O que é limite estimado? Posso ignorar?** Quando a via não tem limite cadastrado, o
Pardal estima pela regra geral do Código de Trânsito para aquele tipo de via e marca a linha
com `estimated=1`. Pode estar errado. Para usar só limites sinalizados, descarte as linhas com
`estimated=1` (no consolidado do Brasil eles já vêm num arquivo separado).

**O radar vale para qual sentido?** Veja a coluna `direction_deg`: é o rumo do trânsito
fiscalizado, em graus (0 = norte, 90 = leste, 180 = sul, 270 = oeste). Compare com o rumo do
veículo: num app de alerta, ignore o radar só se a diferença passar de 60° (com GPS preciso e em
movimento). Vazio quer dizer os dois sentidos **ou** sentido desconhecido, sem como separar: avise
nos dois. De onde vem o sentido, e por que o gerador usa 90° e o app 60°: "Sentido do radar", na
seção Formato.

**Como sei se um radar ainda funciona?** A coluna `active` usa a situação informada pela
ANTT e pelos DERs, nas rodovias federais a validade da aferição no Inmetro e, na cidade de São
Paulo, os locais que a CET desativou.

**O que é um radar com fonte `INMETRO`?** O Inmetro registra todo medidor de velocidade aferido
do país, com a velocidade e a validade da aferição, mas sem coordenada: só o endereço. Quando o
endereço é "rua + número" ou um cruzamento, a posição vem do cadastro de endereços do IBGE (Censo
2022). Se há um radar conhecido a até 100 m, é o mesmo: ele ganha `+INMETRO` na coluna `source`
(aferição válida confirmada) e o limite, se não tinha. Se não há, sai um radar novo com
`source=INMETRO`. A posição desses é a do endereço, menos exata que a das outras fontes: medida
nas cinco capitais que têm lista oficial com coordenada, fica a 23 m do radar na mediana e a até
100 m em 89% dos casos; cerca de 1 em cada 10 pode estar a mais de 100 m do lugar certo.

**O mesmo radar aparece duas vezes?** Não: quando o OpenStreetMap e uma fonte oficial trazem o
mesmo radar (a até 30 m), ou dois órgãos publicam o mesmo radar, fica um ponto só, com a
posição, o limite e o sentido da fonte oficial, e a coluna `source` lista as fontes que o
confirmam. Pontos do OpenStreetMap a até 8 m um do outro também viram um só. Radares próximos
do mesmo órgão continuam separados: são equipamentos diferentes (um por pista, por faixa ou por
aproximação de cruzamento).

**Em que estado fica um ponto na divisa ou numa ponte?** Em um só: no estado cujo contorno
(malha oficial do IBGE) contém o ponto; ponte, orla e ilha que ficam fora do contorno vão para o
estado mais perto, a até 5 km. Ponte ou túnel na divisa sai nos dois estados.

**Posso usar no meu app ou projeto?** Pode, seguindo a licença ODbL (abaixo): citar as
fontes e manter a mesma licença em bases derivadas.

## Cobertura e limitações

- **Não é fonte oficial.** O conjunto junta o que os órgãos publicam e o que o OpenStreetMap mapeia: um radar novo,
  removido ou desligado pode demorar a aparecer, e o radar que nenhuma fonte publica não está aqui.
- **A cobertura muda de estado para estado.** Na edição de 2026-11-08, em 12 UFs (AC, AL, AM, AP, ES, MS, MT, PA, PI,
  RN, RR e SC) os radares vêm só das fontes federais e do OpenStreetMap, sem órgão estadual nem municipal. O
  `coverage` de cada UF no catálogo diz quais fontes entraram.
- **Sentido:** só 17,9% dos radares têm `direction_deg` (geração de 2026-11-08), e o vazio não separa "os dois
  sentidos" de "desconhecido" (ver "Sentido do radar").
- **Posição aproximada** nos radares que só o Inmetro conhece (pelo endereço: cerca de 1 em 10 fica a mais de 100 m)
  e nos trechos postos pelo km do SNV (radar portátil, buracos, acidentes com moto); o banco SQLite traz essa margem
  em `position_accuracy_m`.
- **Limite estimado** (`estimated=1`) é a regra geral do Código de Trânsito para o tipo de via, não a placa, e só
  existe na rede principal.
- **Câmeras de outras infrações** só em SP, MG e PR (São Paulo, Belo Horizonte e Curitiba publicam os locais com
  coordenada); **pedágios sem preço**.
- **O repositório pode estar até uma semana atrás** da release mais nova; o `limites_trechos.csv` e o banco SQLite só
  existem na release.
- **Fonte fora do ar** fica com a última leitura boa; a data do dado de cada fonte está em `source_dates`.

## Geração e reprodutibilidade

O código que baixa as fontes, junta, calcula o sentido e gera todos os arquivos está em
[`gerador/`](gerador) (Python). Lá estão como rodar, como funciona cada parte, a
investigação das fontes com as medições ([`FONTES.md`](gerador/FONTES.md)) e o que ainda
falta ([`PENDENCIAS.md`](gerador/PENDENCIAS.md)).

| O quê | Quando | Onde |
|---|---|---|
| Geração completa e **release** `dados-AAAA-MM-DD` (zips por estado, Brasil, catálogo e sha256; a partir da próxima, também os bancos SQLite) | **todo dia**, se algum arquivo mudou em relação à última release (dia sem dado novo não gera release) | Releases; `releases/latest/download/pardal-<UF>.zip` traz sempre a mais nova |
| **Commit** dos arquivos do repositório (`brasil/`, `estados/`, `catalogo.json`) | **uma vez por semana**: na primeira geração que passar a partir do **domingo** (se o domingo falhar, segunda tenta de novo, e assim por diante) | este repositório |
| **Retenção** | releases com mais de **90 dias** são apagadas, menos as semanais (as que foram para o repositório) e a mais nova | — |

A geração dispara às 03:17 de Brasília e de novo às 09:17, que só gera se a primeira não tiver
passado; o GitHub às vezes atrasa ou pula disparos agendados. Por isso o repositório pode estar até
uma semana atrás da release mais nova: para o dado mais novo, use a release. Arquivo acima de 95 MB
(o GitHub recusa a partir de 100 MB) sai compactado (`.csv.gz`), e o catálogo aponta para ele.

Cada fonte é atualizada quando responde; uma fonte fora do ar fica com a última leitura boa (ou com
o que tinha na edição anterior), e as outras seguem normalmente. A data do dado de cada fonte está no
campo `source_dates` do `catalogo.json`, e a data de cada pacote, no campo `built_at`.

Se uma geração agendada falhar, a release anterior continua no ar e fica aberta uma
[issue](https://github.com/Murkiriel/pardal/issues) "Geração falhando" até a próxima passar.

**Só a geração corrente é reproduzível.** O código, o Python 3.12, as dependências (todas, transitivas incluídas, com
versão exata e hash: `gerador/requirements.in` → `gerador/requirements.txt`, instaladas com
`pip install --require-hashes`) e as actions do GitHub (pelo SHA do commit) ficam travados, mas as fontes são
lidas ao vivo e não são arquivadas, e as cópias guardadas delas ficam só no cache do GitHub Actions, que some depois
de 7 dias sem uso. Uma geração antiga não se refaz: para ter o dado de uma data, guarde a release dela.

## Licença e atribuição

Os **dados** são uma base derivada do OpenStreetMap, distribuída sob a
**Open Database License (ODbL) 1.0** (texto em [`LICENSE`](LICENSE)).

- Cite "© colaboradores do OpenStreetMap" e as fontes da tabela abaixo.
- Se você publicar uma base derivada deste conjunto, ela precisa manter a ODbL.
- Cada zip da release traz um `LICENCA-DADOS.txt` com este aviso e as fontes daquele pacote; o banco SQLite traz
  a atribuição na tabela `meta`.

O **código** (pastas `gerador/` e `scripts/`) é **MIT** ([`gerador/LICENSE`](gerador/LICENSE)).

### Fontes

| Fonte | O que entra | Licença |
|---|---|---|
| OpenStreetMap (extratos da Geofabrik) | Radares, limites (`maxspeed`), pontes e túneis | ODbL 1.0 — © colaboradores do OpenStreetMap |
| DNIT — Controle de Velocidade (PNCV) | Radares das rodovias federais, com o sentido fiscalizado | Dado aberto governamental |
| DNIT — Sistema Nacional de Viação | Quilometragem das BRs, usada para casar com o Inmetro e para converter o sentido (crescente/decrescente) em rumo | Dado aberto governamental |
| PRF — Trechos aptos à fiscalização com radar portátil | A relação vigente (UF, BR, km inicial e final), posta na rodovia pelo SNV | Dado aberto governamental |
| PRF — Infrações | As multas de velocidade (art. 218) dos 12 meses mais novos, só a contagem por trecho apto ao radar portátil | Dado aberto governamental |
| PRF — Acidentes (agrupados por pessoa) | Os km com 5 ou mais acidentes com moto nos 12 meses mais novos, com os motociclistas mortos, só contagens | Dado aberto governamental |
| PRF — Radares fixos (planilha das concessões que a página oficial mostra) | A situação de cada equipamento das concessões federais (ativo, inoperante, estudo ou aferição vencidos) e a coordenada dos ativos; o radar inoperante ou vencido sai inativo, o ativo que nenhuma outra fonte tem entra com `source=PRF` | Sem licença escrita: tabela externa (Apps Script) apontada pela página da PRF |
| SIE-SC — Locais de operação do radar portátil | Rodovia SC, km e sentido; o km posto na via entre os marcos quilométricos do OSM | Dado aberto governamental |
| DNIT — Condições do Pavimento (ICM) | Os km com panela ruim ou péssima do levantamento mais novo, postos na rodovia pelo SNV | Dado aberto governamental |
| ANTT — Radar | Radares das concessões federais, com situação e sentido | CC-BY |
| ANTT — Sinalização | Placas de velocidade máxima das concessões federais, por sentido | CC-BY |
| Inmetro — PSIE, medidores de velocidade | Situação da aferição (ativo/inativo) e, nas rodovias federais e nas estaduais de SP (DER-SP), o limite do radar que não trazia nenhum; nos medidores com endereço urbano, a confirmação do radar, o limite e os radares que nenhuma outra fonte tem | Creative Commons |
| DER-SP / Artesp, DER-GO (Goinfra), DER-PE | Radares das rodovias estaduais, com o sentido fiscalizado (SP e GO) | Dado aberto governamental |
| DER-SE, AGETO-TO, Detran-MA, SEINFRA-BA | Radares e lombadas eletrônicas das rodovias estaduais de Sergipe, Tocantins, Maranhão e Bahia, com limite | Dado aberto governamental |
| DER-MG | Radares fixos das rodovias estaduais e federais delegadas de Minas Gerais (rodovia + km, postos na via pela malha estadual da IDE-Sisema e pelo SNV, conferidos pelo município) | Dado aberto governamental |
| IDE-Sisema (SEMAD-MG) — rodovias estaduais e federais de Minas Gerais | Quilometragem das MG, para pôr os radares do DER-MG na via | Dado aberto governamental |
| Goinfra — malha rodoviária estadual | Quilometragem das rodovias de Goiás, para converter o sentido em rumo | Dado aberto governamental |
| IBGE — malha das unidades da federação (API de malhas) | Contorno de cada estado, para decidir em que estado fica cada ponto | Dado aberto governamental |
| IBGE — CNEFE, cadastro de endereços do Censo 2022 | Coordenada do endereço dos medidores do Inmetro que só informam rua e número ou um cruzamento | Dado aberto governamental |
| Prefeitura do Rio de Janeiro (IPP, SMTR/CET-Rio) | Limite por trecho de rua e radares da cidade | CC-BY 4.0 |
| Prefeitura de São Paulo (GeoSampa, CET) | Limite pela classificação viária (vias de trânsito rápido e arteriais) e os radares ativos da cidade (locais fiscalizados da CET, com limite e sentido centro/bairro; reserva: o CSV que a CET publica no GitHub) | Dado aberto municipal |
| BHTrans (Belo Horizonte) | Radares e detectores de avanço de sinal | CC-BY |
| Detran-DF | Radares e lombadas eletrônicas | Dado aberto governamental |
| Prefeituras de Fortaleza, Recife, João Pessoa e Curitiba | Radares urbanos | Dado aberto governamental |
| EPTC (Porto Alegre) | Radares fixos, lombadas eletrônicas e detectores de avanço de sinal, com limite (relatório público da EPTC) | Dado aberto municipal |
| Transalvador (Salvador) | Radares fixos, com limite (mapa de equipamentos da Transalvador) | Dado aberto municipal |
| SEMTRAN (Porto Velho) | Radares fixos, com a validade da aferição (planilha publicada pela SEMTRAN) | Dado aberto municipal |

## Projetos irmãos

Quatro geradores independentes de dados abertos do Brasil para uso offline, um pacote por UF:

- [**Carcará**](https://github.com/Murkiriel/carcara): o mapa base, em PMTiles.
- [**Andorinha**](https://github.com/Murkiriel/andorinha): as rotas, em tiles do Valhalla.
- [**Sabiá**](https://github.com/Murkiriel/sabia): a busca de lugares e endereços, em SQLite.
- **Pardal** (este): os radares e os limites de velocidade, em CSV, GeoJSON, KML, GPX e SQLite.

Os quatro dividem o país nas mesmas 27 UFs, pelos limites do IBGE, e publicam um `catalogo.json` com o `sha256` de
cada arquivo e o `bbox` de cada UF em `[lat_min, lon_min, lat_max, lon_max]`, no WGS84. Carcará, Andorinha e Sabiá
seguem o mesmo molde de catálogo e de release (`schema` 1, `build_id` como etiqueta da release, `release_url`,
`base` e `states`); o catálogo do Pardal tem formato próprio (`ufs`) e um `bbox` aproximado. O banco SQLite do Pardal
segue as convenções do Sabiá: coordenadas em inteiros × 100.000, latitude primeiro, e a mesma célula do zoom 13.

## English

**Pardal** is an open dataset of **speed cameras in Brazil** (fixed cameras, average-speed
sections, red-light cameras, with the enforced direction as a compass bearing) and **road speed limits**, with coordinates, as CSV, GeoJSON,
KML and GPX, for the whole country (`brasil/`) and per state (`estados/<UF>/`), plus one SQLite database per
state in the GitHub release (`pardal-<UF>.sqlite.zst`, from the next release on). It merges
official Brazilian open data (DNIT, ANTT, Inmetro, state road agencies, city halls) with
OpenStreetMap. Coordinates are WGS84; mind the order: CSV columns are `lat,lng`, GeoJSON is
`[lng, lat]` and WKT is `lng lat`; the catalogue `bbox` is `[lat_min, lon_min, lat_max, lon_max]`. Regenerated daily as a GitHub release (when anything changed);
the files in the repository are updated weekly; releases older than 90 days are pruned, except the
weekly ones. Only the current generation is reproducible: dependencies are locked with hashes and actions
pinned by commit SHA, but the live sources are not archived. Data licensed under the ODbL 1.0; the generator code (`gerador/`, Python) under
MIT. Not an official source; road signs always prevail. Sister projects: basemap
([Carcará](https://github.com/Murkiriel/carcara)), routing ([Andorinha](https://github.com/Murkiriel/andorinha)) and
search ([Sabiá](https://github.com/Murkiriel/sabia)).

<sub>Palavras-chave: radares Brasil, lista de radares, localização de radares, base de
radares, radares fixos, pardais, lombada eletrônica, radar de trecho, avanço de sinal,
fiscalização eletrônica, limite de velocidade, velocidade máxima das vias, rodovias
federais, rodovias estaduais, DNIT, ANTT, Inmetro, DER, arquivo de radares para GPS, POI de
radar, sentido do radar, GPX, KML, CSV, GeoJSON, OpenStreetMap, dados abertos, Brazil speed cameras, speed
limits Brazil, open data.</sub>
