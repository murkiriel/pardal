# Investigação de fontes — radares, limites e estruturas (2026-09-29)

Levantamento para a nova geração dos pacotes antes de publicar o conjunto de dados. Cada
fonte abaixo foi **baixada e aberta** (não só vista num buscador), salvo onde indicado.

Base atual (pacotes de 2026-09-09): 15.702 radares (9.841 OSM, 1.708 DNIT, 1.647 DER-SP,
1.113 ANTT, 1.018 DER-GO, 193 Fortaleza, 79 Recife, 75 João Pessoa, 28 DER-PE), 1,24 milhão
de pontos de limite, 126 mil estruturas.

## Referência nacional: Inmetro (PSIE)

`https://servicos.rbmlq.gov.br/dados-abertos/{UF}/medidores.json` — JSON mensal por UF,
licença Creative Commons (metadados: `dados-abertos/metadados_medidores_velocidade.pdf`).
Todo medidor de velocidade aferido no país, de qualquer órgão: local (`LocalVerificacao`,
rodovia+km ou endereço), município, faixas com sentido e **velocidade**, validade da
aferição e último resultado. **Sem coordenada.** (DF volta vazio; está dentro de GO.)

| | Fixos | Válidos e aprovados em 2026-09-29 | Com rodovia+km |
|---|---|---|---|
| Brasil (26 UFs) | 34.043 | **17.118** | 8.192 |
| GO (inclui Brasília) | 5.433 | 2.760 | 1.709 |
| SP | 8.619 | 4.554 | 1.482 |
| MG | 3.287 | 1.633 | 963 |

Usos: (1) marcar radar ativo/inativo pela aferição, cruzando com as fontes com coordenada;
(2) achar radares que nenhuma outra fonte tem, georreferenciando rodovia+km (ver abaixo) e
endereços (geocodificador).

## A — Com coordenada, prontas para o gerador

| Fonte | O que tem | Formato / licença |
|---|---|---|
| **ANTT — sinalização** (`dados.antt.gov.br/dataset/sinalizacao`) | **14.721 placas de velocidade máxima** das concessões federais: lat/lng, limite leve e pesado, sentido, situação | KMZ, CC-BY, 2026-09-11 |
| **Prefeitura do Rio — trechos de logradouro** (`pgeo3.rio.rj.gov.br/arcgis/rest/services/CadLog/Trechos_Logradouros/MapServer/0`) | `velocidade_regulamentada` em **111.973 de 132.064 trechos** (85% da cidade) | ArcGIS REST; licença a confirmar |
| **Belo Horizonte — fiscalização eletrônica** (`ckan.pbh.gov.br`, `fiscalizacao-eletronica`) | 448 equipamentos: tipo (velocidade, avanço de sinal, faixa exclusiva), limite | CSV mensal, UTM 31983, CC-BY |
| **Belo Horizonte — redutor de velocidade** | 4.748 lombadas físicas | CSV mensal, CC-BY |
| **DF — Detran (ArcGIS `Base_DETRAN`)** | 1.125 radares (lat/lng, limite) + 1.230 lombadas eletrônicas | ArcGIS REST, dados de 2019 |
| **DF — portal de dados abertos** | versão atual do mesmo cadastro | CSV; o portal bloqueia download automático (baixar no navegador) |
| Mogi das Cruzes (ArcGIS `radares`) | 14 radares | ArcGIS REST |
| **Curitiba — fiscalização eletrônica da Setran** (`transito.curitiba.pr.gov.br/fiscalizacaoeletronica`, desde 2026-10-05) | 308 pontos em operação: coordenada, identificação, o que fiscaliza (velocidade, avanço de sinal, parada na faixa, conversão), limite | Página HTML (a lista inteira numa página só) |
| **Porto Alegre — EPTC, medidores eletrônicos de velocidade** (relatório Power BI público ligado à página da EPTC, desde 2026-10-05) | 155 medidores: coordenada, sentido, limite, tipo (pardal, lombada, DAS, portátil), situação | Power BI "publicar na web", como o da CET-SP |
| **DER-SE** (`der.se.gov.br/localizacao-de-radares-fixos`, desde 2026-11-08) | 129 radares e lombadas das rodovias estaduais: coordenada, limite | Planilha Google publicada na web (CSV) |
| **AGETO-TO** (`to.gov.br/ageto/lista-de-radares`, desde 2026-11-08) | 58 radares, barreiras eletrônicas e mistos das rodovias estaduais: coordenada, limite, nº Inmetro | PDF |
| **Detran-MA** (página de fiscalização eletrônica, desde 2026-11-08) | 33 radares das rodovias estaduais: coordenada, limite, sentido nominal | PDF |
| **SEINFRA-BA** (`ba.gov.br/infraestrutura/12046/mapas`, desde 2026-11-08) | 78 radares das rodovias estaduais: coordenada, limite, rodovia + km | PDF (o KML vem num RAR) |
| **Transalvador** (mapa de pórticos do transonline, desde 2026-11-08) | 102 radares de Salvador: coordenada, limite, série | Página HTML (marcadores do Google Maps) |
| **SEMTRAN Porto Velho** (página "radares fixos", desde 2026-11-08) | 39 radares: coordenada, validade da aferição | PDF |

## B — Rodovia + km (precisam de referência linear)

- **DER-MG**: 708 radares fixos com limite (tabela HTML, atualizada 2026-09-29).
- **DAER-RS, fixos e lombadas** (conferido em 2026-11-08): ao contrário do que a linha abaixo dizia, a
  página `daer.rs.gov.br/pardais` liga um PDF com cada pardal por rodovia RS + km (60 equipamentos, com
  série e nº Inmetro), e `localizacao-das-lombadas` outro com 131 redutores. Sem coordenada.
- **DER-ES** (`servicos.der.es.gov.br/Radares.aspx`, conferido em 2026-11-08): 392 registros com código,
  endereço com rodovia + km, faixas, tipo, velocidade e série; sem coordenada.
- **DER-RJ, radar portátil** (`sgitp.der.rj.gov.br/radares-portateis`): 41 locais por rodovia + km; o
  certificado do site estava vencido em 2026-11-08.
- **DER-PR, DAER-RS, DER-ES**: listas em PDF (a obrigação vem da Res. Contran 798/2020).
  DAER-RS não publica o ponto exato dos pardais, só os trechos.
  DER-PR (conferido em 2026-10-09): a página "Fiscalização por equipamento fixo" traz um só PDF, o da EPR Litoral
  Pioneiro (12 controladores nas PR-407, PR-151 e PR-092, rodovia + km, sem coordenada). É concessão federal da ANTT:
  nos sete municípios do PDF o pacote do PR já tem os radares da ANTT (Arapoti 4, Sengés 2, Siqueira Campos 2, Castro,
  Carambeí, Piraí do Sul, Paranaguá). Sem ganho; e sem malha estadual do PR com km em aberto, o km não teria onde cair.
- **SIE-SC, radar portátil** (conferido em 2026-10-09): SC não tem radar fixo estadual; a SIE publica os locais de
  operação do radar portátil da PMRv (`sie.sc.gov.br/webdocs/sie/consultamultas/radares/`, PDF de 12 páginas, válido
  desde 16/05/2023): 596 pontos em rodovias SC, cada um com código, rodovia, km, sentido (crescente/decrescente),
  município e limite. Sem coordenada e sem malha estadual com km em aberto; o OSM tem 3.958 marcos quilométricos
  (`highway=milestone` com `distance` e `ref`) em 67 rodovias SC: 462 dos 596 pontos ficam entre dois marcos da própria
  rodovia, 327 com marco a até 5 km dos dois lados (SC-161, SC-157, SC-453, SC-305 sem marcos). Posição: pelo caminho
  das vias `ref=SC-N` entre os dois marcos, não pela reta.
- **Inmetro**: 8.192 válidos com rodovia+km no país.

Referência linear disponível:
- **Federais: SNV Rotas do DNIT** (`servicos.dnit.gov.br/dnitcloud`, pasta "SNV Rotas",
  `rota_202607A.zip`) — 733 rotas PolylineM com o km em cada vértice → interpolação exata.
  A base geométrica (`202607A.zip`, 7.673 trechos) traz `est_coinc` (estadual coincidente).
- **Estaduais**: sem base nacional. Marcos quilométricos no OSM (`highway=milestone`):
  ~11.400 (SC 3.968, SP 1.575, sul federais 1.526; resto esparso). SREs estaduais achados:
  DAER-RS (i3geo), SC (DEINFRA, já importado no OSM); MT (servidor Sinfra fora do ar);
  MG (IDE-Sisema, sem km confirmado).

## C — Só endereço (precisam de geocodificação)

- **Rio de Janeiro** (SMTR/CET-Rio): PDF de 36 páginas com endereço, código e limite
  (atualizado 2026-09-11). A própria prefeitura tem geocodificador com número de porta
  (`pgeo3.../Geocode/Geocode_NP`, `Geocode_Logradouros_WGS84`).
- **Inmetro**: ~8.900 válidos com endereço urbano (Brasília 1.013, Goiânia 291, …).
- CET-SP (mapa), Goiânia (consulta na tela) — sem arquivo aberto. Salvador saiu desta lista em
  2026-11-08 (seção A): o mapa de pórticos da Transalvador traz a coordenada de cada radar.
- Manaus (IMMU, página "Consulta Aferição dos Radares", `immu.manaus.am.gov.br/index.php?r=site%2Finforadar`),
  Aracaju (SMTT, `smtt.aracaju.se.gov.br/wp-json/smtt/v1/radares`, 44 medidores com situação e limite),
  Araguaína-TO (PDF da ASTT): endereço e sentido, sem coordenada (achados em 2026-11-08, ver abaixo).
  Curitiba e Porto Alegre saíram desta lista em 2026-10-05 (seção A): a página da Setran passou a trazer
  a coordenada, e o relatório Power BI da EPTC tem a tabela dos medidores com ela.

## D — Indisponíveis agora

- ~~**Seinfra-BA**~~: voltou depois da eleição; entrou como fonte em 2026-11-08 (seção A, pela lista
  em PDF de 15/09/2026).
- **SC**: sem radar em rodovia estadual há 14 anos; contrato de retomada suspenso em maio/2026.
- DNIT: o portal só tem `controle-de-velocidade` como dado útil (já usado); sem inventário
  de placas das federais não concedidas.

## Descartadas (licença)

MapaRadar (CC BY-NC-ND), radarnobrasil.com e RecursoDeMulta (colaborativos, sem licença de
redistribuição), bases comerciais, Waze/Google (sem API, termos proíbem).

## Recomendação para esta geração

1. **Entrar agora** (baixo esforço, alto ganho): placas de velocidade da ANTT, trechos do Rio,
   BH (radares + lombadas), DF Detran (ArcGIS), e Inmetro como **status ativo/inativo**
   cruzando por município + rodovia + km com as fontes que já têm coordenada.
2. **Referência linear federal (SNV Rotas)**: georreferenciar os registros "BR-xxx km" do
   Inmetro e do DER-MG que não casarem com nenhuma coordenada existente.
3. **Estaduais por marcos do OSM** onde houver densidade (SC, SP); resto fica para quando
   houver SRE com km.
4. **Geocodificação**: Rio pelo geocodificador da prefeitura; o resto depois.
5. Rodar de novo depois da eleição para BA e outros sites suspensos.

## Resultado da implementação (2026-09-29)

| Frente | O que entrou | Medição |
|---|---|---|
| Placas ANTT | `sources/antt_placas.py`: placa projetada na rota do SNV da própria BR, vale até a próxima do mesmo sentido (máx. 10 km), pontos a cada 200 m; sentidos em desacordo não emitiam nada (desde a seção "Sentido" abaixo: um ponto por sentido) | 14.517 placas ativas, 13.421 casadas no SNV, 33.583 pontos (~6.700 km) |
| Rio — trechos | `sources/rio.py`: vértices + preenchimento a 150 m | 208.986 pontos |
| Rio — radares | PDF da SMTR + geocodificador de número de porta da prefeitura (score ≥ 95) | 1.083 itens (599 velocidade, 484 avanço de sinal), 615 geocodificados |
| BH / DF | `sources/bh.py` (UTM 23S, via curl: o WAF da PBH barra o TLS do Python), `sources/df_detran.py` | 396 / 2.355 |
| Inmetro | `inmetro_status.py`: casa por km na mesma BR/UF fora de concessão; só mexe em OSM, DNIT, DER-GO, Detran-DF — num radar juntado, só se todas as fontes oficiais dele forem dessas (`ANTT+OSM` fica com a situação da ANTT; antes bastava uma parte, e 1.393 radares publicados entravam indevidamente na regra). Radar do DNIT casa pelo km da própria planilha (o mesmo do Inmetro; em Itaberaí, BR-070, o SNV punha o radar 1,9 km longe do km 189,8), os outros pelo km do SNV. Radar confirmado sem limite ganha a velocidade nominal do medidor (o de km mais perto; empate, a menor). Desde 2026-10-05 o índice tem também as rodovias estaduais, e o DER-SP (Artesp e planilha própria, com situação própria) casa pelo km das planilhas dele e ganha **só o limite** (ver "Radares sem limite, por fonte") | GO: 71 confirmados / 2 desativados, 58 ganharam limite (dos 69 do DNIT, 8 seguem sem); MG: 129 / 21 (antes do limite) |
| Limites oficiais x OSM | `model.override_limits`: pontos do OSM a < 50 m de um oficial saem, para o valor não alternar entre as duas fontes no mesmo trecho | — |

**Descartado depois de medir:** criar radar novo a partir de "rodovia + km".
- SNV contra os 1.774 radares do DNIT (coordenada + km): mediana 226 m, p75 873 m, só 34% a ≤ 100 m.
- Marcos quilométricos do OSM (por UF): mediana 83 m, mas 25% > 200 m e só ~100 casos fora de SC.
- O km das placas ANTT é o da concessão (PNV antigo): BR-381/MG km 480,5 cai 7 km longe no SNV atual.

## Radares sem limite, por fonte (2026-10-05)

Contagem nos dados publicados em 2026-10-03 (`brasil/radares.csv`, depois do limite do Inmetro
para o DNIT): 4.933 dos 19.020 radares ativos saem sem limite.

| Fonte (ativos) | Total | Sem limite |
|---|---|---|
| DETRAN-DF | 2.196 | 1.326 |
| OSM | 7.281 | 1.294 |
| DER-SP | 1.268 | 1.268 (todos) |
| INMETRO (só endereço) | 1.784 | 325 |
| BHTRANS | 260 | 179 |
| RIO | 290 | 178 |
| DNIT | 1.030 | 174 |
| PMF | 72 | 72 |
| CET-SP | 256 | 36 |
| ANTT, DER-GO, ANTT+OSM, DER-GO+OSM | 2.108 | 0 |

ANTT e DER-GO já trazem o limite de todo radar: casar o km deles com o Inmetro não acrescenta nada.
O buraco grande era o DER-SP: as duas planilhas (Artesp e a do DER) não têm limite, mas têm rodovia
e km ("SP330" + "km 060+550"; "SP 008" + 96,86), o mesmo cadastro do Inmetro, que lista 1.702
medidores fixos em rodovia estadual de SP (1.125 válidos, com velocidade nominal). Casando pelo km
das planilhas, como o DNIT:

- concordância com o OSM nos radares DER-SP+OSM que já tinham limite: 302 de 320 iguais (janela de
  1 km; 225 de 240 a 50 m). Quase toda diferença é OSM 110 e medidor 90 ou 100;
- situação: continua a do DER-SP (status da Artesp, cancelamento do DER); o Inmetro só dá o limite;
- SP gerado localmente: radares DER-SP ativos sem limite de 1.301 para 456 (845 ganharam limite);
  os das outras fontes ficaram iguais (793). No estado, os ativos sem limite foram de 2.094 para 1.249.

Os que sobram no DER-SP: acesso (SPA, SPI, sem km que case), medidor só vencido ou reprovado perto,
ou nenhum medidor no km. De passagem: "KM 004" deixou de ser lido como a rodovia "KM-4" (no
Inmetro de SP, "SPA-372/321 KM 004,000"); 618 medidores válidos do país saem dessa falsa rodovia, e
um deles, um cruzamento em Rio Claro, passa a poder ser localizado pelo endereço.

### Curitiba — página da Setran (2026-10-05)

`sources/municipal.py`, fonte `CURITIBA`. Cada item da página de fiscalização eletrônica traz o
ponto (`verNoMapa('lat','lng')`), a identificação ("RADAR AR-15", "Radar MO-07A"), os tipos de
fiscalização (títulos dos ícones) e o limite (classe `icn-velocidade-NN`). Velocidade controlada vira
radar fixo; só avanço de sinal vira avanço de sinal; só conversão proibida fica de fora, como no BH.
Na leitura de 2026-10-05: 308 pontos, 293 de velocidade (274 com limite: 50 km/h 142, 40 km/h 65,
60 km/h 40, 70 km/h 27) e 15 só de sinal. Sem sentido publicado (as letras A, B, C da identificação
separam faixas ou sentidos, sem dizer qual).

PR gerado localmente, área de Curitiba: radares ativos de 420 para 542. Dos 308 pontos, 165 se
juntam a radares que já estavam (111 do OSM, 29 do Inmetro por endereço, 25 dos dois) e 143 entram
novos (128 de velocidade e 15 de sinal). Observação: 25 desses novos têm um radar só do OSM entre
30 e 50 m, fora do raio de junção (30 m, o mesmo para todas as fontes); podem ser o mesmo
equipamento mapeado longe ou o do outro sentido. Fica anotado, sem mudar a regra.

### Porto Alegre — relatório da EPTC (2026-10-05)

`sources/eptc.py`, fonte `EPTC`. A página "Medidores Eletrônicos de Velocidade" da EPTC liga dois
relatórios Power BI públicos. O de localização ("Localização da Fiscalização por Equipamentos
Eletrônicos") tem a tabela `BaseMevFluxo`, lida como a da CET-SP (`_powerbi.py`), com a cópia da última
leitura boa em `data/raw/` se a API falhar. O relatório fica no cluster do norte da Europa do Power BI
(o endereço de roteamento responde 403; achado testando os clusters). O outro relatório (fluxo e
infrações) tem uma tabela de autos com placa de veículo: não é lido.

Na leitura de 2026-10-05: 155 medidores, todos "Ativo": 46 pardais, 39 lombadas eletrônicas, 11 DAS
(detector de avanço de sinal que também mede velocidade) e 59 portáteis. Os três primeiros viram radar
fixo (96, todos com limite: 60 km/h 46, 40 km/h 38, 30 km/h 10, 80 km/h 2); o portátil é ponto de
operação do radar móvel e fica de fora. Limite com dois valores ("40km/h_60km/h"): o menor. O sentido
(BC/CB, NS/SN, IC/CI) ainda não é usado.

RS gerado localmente, área de Porto Alegre: radares ativos de 147 para 192. Dos 96, 47 se juntam a
radares que já estavam (33 do OSM, 8 do Inmetro, 6 dos dois) e 49 entram novos; 6 dos novos têm um
radar só do OSM entre 30 e 50 m (como em Curitiba, fora do raio de junção).

### Órgãos estaduais e capitais achados em 2026-11-08

Origem: a lista de coletores do projeto Bunda-de-Urso (`github.com/Challado/Bunda-de-Urso`, cadastro
de radares de várias fontes oficiais; código "fonte disponível", não livre, e compilação CC BY 4.0).
O projeto serviu só de mapa: cada fonte abaixo foi baixada e lida direto do órgão. Outros projetos
olhados no mesmo dia e descartados por só repetirem fontes que já entram aqui (OSM, DNIT, ANTT, CET,
Inmetro ou os próprios pacotes do Pardal): radar-na-rota, ohm-maps-dados, radarsp (zzzzghst7, que também
usa o radarnobrasil, sem licença), pardal (olegantonov), pardal-teste, Efisc; open-radars-manaus (7
pontos levantados em campo, ODbL) e fiscalizacao-eletronica (8 pontos de São José dos Pinhais de 2023,
sem origem) por serem pequenos demais.

Leitura de 2026-11-08 e distância de cada ponto ao radar mais perto de `brasil/radares.csv` (pacote
publicado antes delas):

| Fonte (`source`) | Módulo | Pontos | Já no pacote a ≤ 50 m | Novos (> 200 m) | Observações |
|---|---|---|---|---|---|
| `AGETO-TO` | `sources/ageto_to.py` | 58 | 0 | 57 | 40 radares fixos, 16 barreiras eletrônicas, 2 mistos; todos com limite |
| `DER-SE` | `sources/der_se.py` | 129 | 5 | 124 | coordenada no link do Maps (`query=` ou `!3d!4d`), em graus/minutos/segundos ou num link curto (9), aberto pelo redirecionamento; limite 50 ou 40 |
| `SEINFRA-BA` | `sources/seinfra_ba.py` | 78 | 5 | 67 | lista de 15/09/2026; um ponto com a longitude sem o "-" (corrigido: a BA inteira é sul/oeste) |
| `DETRAN-MA` | `sources/detran_ma.py` | 33 | 1 | 31 | 68 linhas (uma por sentido e faixa); todos 60 km/h |
| `TRANSALVADOR` | `sources/transalvador.py` | 102 | 27 | 69 | data de aferição velha na página (52 de 2022): não desativa nada |
| `SEMTRAN-PVH` | `sources/semtran_pvh.py` | 39 | 15 | 9 | sem limite; coordenada estragada pela planilha ("-876.651.999.999.999.000" = -8,76652), refeita pelo número de dígitos inteiros; ativo enquanto a validade da aferição não venceu (38) |

Todas entram como FIXED (lombada e barreira eletrônica medem velocidade), sem sentido (o Detran-MA e a
Transalvador dão só o nominal, "LESTE/OESTE", "SENTIDO AEROPORTO"). Cada uma tem a sua entrada no
`OFFICIAL` do `build.py` e, por isso, a sua cópia da última leitura boa (`source_cache`). A UF do órgão
está em `common/ufs.py` (`_drop_far_from_home`); no catálogo, AGETO-TO, Detran-MA e SEINFRA-BA contam
como cobertura estadual e Transalvador e SEMTRAN-PVH como municipal.

Build real de TO, MA, SE, BA e RO em 2026-11-08 (servidores reais, extratos do OSM de 29/09), radares
no pacote antes → depois: TO 77 → 136, MA 145 → 176, SE 131 → 255, BA 463 → 618, RO 35 → 61; nenhuma
falha nem aviso das seis fontes. No pacote: AGETO-TO 58, Detran-MA 33, DER-SE 129 e SEINFRA-BA 77, todos
com limite; Transalvador 102 (98 com limite); SEMTRAN-PVH 38 (12 com limite, vindo da junção, 37 ativos).
Radar novo a 30–100 m de um de outra fonte, fora do raio de junção (30 m): SEINFRA-BA 7, Transalvador 5,
AGETO-TO 1, DER-SE 1. Em Salvador e na BA-526 há também pares da mesma fonte a 30–100 m com o mesmo
limite, nos dois lados da via: são os dois sentidos, publicados como equipamentos separados. Como em
Curitiba e Porto Alegre, fica anotado, sem mudar a regra de junção.

Achadas e **não** integradas (sem coordenada; criar radar a partir de rodovia + km foi descartado depois
de medir, seção "Resultado da implementação", e endereço sem número cai no meio da rua): DAER-RS (fixos e
lombadas, rodovia + km), DER-ES (392, rodovia + km), DER-RJ (radar portátil, rodovia + km), SMTT Aracaju
(44, endereço; API JSON), IMMU Manaus (endereço e sentido), Araguaína-TO (endereço), Cariacica-ES (13
pontos num mapa do Google My Maps ligado pela prefeitura; candidata, não medida), Joinville-SC (PDF bienal,
parte dos itens com GPS; candidata, não medida). Campo Grande, Macapá, Boa Vista, Cuiabá, Teresina e
Belém só têm notícia ou portaria, sem lista.

### Pontos de atenção do OSM (2026-11-08)

Ideia tirada dos apps de alerta Super Tripper (Pod e Dash), que além dos radares avisam de perigos na via e de pontos de
atenção. A base deles não serve: mistura a SCDB.info (comercial; os termos proíbem repassar os dados), o OSM e o DNIT
sem dizer a origem de cada ponto (análise em `~/APKs/RADARES-OFFLINE.md`). O que entrou aqui vem só do OSM:
`osm_pbf.load_hazards`, arquivo `pontos_atencao.csv` por estado (pacote schema 9). Etiquetas: `railway=level_crossing`
(passagem de nível), `highway=speed_display` (painel de velocidade) e `hazard=*` (os valores da wiki agrupados em curva,
cruzamento perigoso, travessia de animais, área escolar e queda de barreira; o resto vira `HAZARD`).

Leitura dos extratos de 2026-11-08 (38 s nas cinco regiões): 19.174 pontos, 17.391 passagens de nível, 793 `HAZARD`,
467 curvas, 332 painéis de velocidade, 116 áreas escolares, 31 travessias de animais, 31 quedas de barreira e 13
cruzamentos perigosos. Ficaram de fora: semáforos (`highway=traffic_signals`, mais de 12 mil só no Norte, Nordeste e
Centro-Oeste, que não pedem aviso), travessias de pedestre e placas de pare e de dê a preferência.

Também da análise dos mesmos apps, as recomendações de uso para quem faz app (aviso pela distância na rota, filtro de
sentido só com GPS preciso, grupos de alerta, dois avisos por radar) estão no README, seção "Para quem faz app de alerta".

### Limites como trechos (2026-11-08)

`<UF>/limites_trechos.csv` no zip `pardal-<UF>.zip` da release diária (pacote no schema 10; decidido em 2026-11-08: só na
release, não no repositório, porque somam ~172 MB e mudam quase todo dia com o OSM; no zip, SP cai de 29,0 para 6,1 MB, MG de
30,6 para 7,3 MB, PR de 11,7 para 2,7 MB). No `catalogo.json` publicado, a entrada `limit_lines` traz `release_asset`,
`asset_path`, `bytes`, `sha256` e `count` (o `publish.rewrite_catalog` troca o `file` do build por esses dois campos). O
limite como a via, não como pontos. Colunas
`limit_kmh,source,estimated,limit_low_kmh,direction_deg,highway,oneway,wkt`; o `limites.csv` não mudou. Código em
`datakit/limit_lines.py` (juntar, cortar, escrever), `osm_pbf.load(..., lines_out=)` (vias do OSM) e `rio.py`, `cet_sp.py`,
`antt_placas.py` (trechos oficiais).

**Do OSM.** Cada via com limite, sinalizado ou estimado, na mesma passada que gera os pontos e com as mesmas regras de
estimativa (`maxspeed`, `maxspeed:forward/backward`, zona sem número, classe da via; tronco/primária/secundária sem `lit`
esperam o fim da leitura para saber se é cidade). Diferenças dos pontos, de propósito:
- *Mão única* (`oneway=yes/-1`, e também autoestrada e rotatória, que o OSM sobreentende): a linha vem desenhada no sentido do
  trânsito (`oneway=-1` é virada) e só vale o limite do sentido que existe; `maxspeed:backward` numa via `oneway=yes` é
  ignorado (os pontos o emitem). `direction_deg` fica vazio: a mão única já diz o sentido, e a coluna `oneway=1` avisa.
- *Mão dupla com `maxspeed:forward` ≠ `backward`*: uma linha por sentido, cada uma desenhada no sentido do trânsito, com
  `direction_deg` = rumo médio. O sentido sem valor ganha a estimativa de sempre, também como linha de um sentido só (os pontos
  a emitem sem sentido).
- `highway` (classe da via) e `oneway` (`1`/`0`) vão para o CSV porque o app (ou o roteador) costuma saber a classe e a mão da
  via em que está: ajudam a escolher entre duas vias paralelas e a não casar uma rua com uma marginal. Nas fontes oficiais
  que não os informam, as duas colunas ficam vazias.
- *Geometria*: Douglas-Peucker a 3 m por via, coordenadas com 5 casas (~1,1 m). Medido em SP (280.926 vias, 110.080 km, antes de
  juntar): sem simplificar 70,4 MB; a 1 m 48,6; a 2 m 40,7; a 3 m 36,8; a 5 m 32,9; a 8 m 30,2 MB. Em 30.000 vias sorteadas, o
  maior desvio de um vértice original para a linha simplificada a 3 m foi de 3,0 m (mediana 1,7 m). Ficou 3 m: abaixo disso o
  arquivo cresce 10-30% sem ganho para casar a via (a largura de uma pista é maior).
- *Juntar* (`limit_lines.join`): vias que se encontram numa ponta (id do nó no OSM, a coordenada nas fontes oficiais) com o mesmo
  limite, fonte, estimativa, classe e sentido viram uma linha só, até 5 km. Só se junta onde exatamente duas pontas se
  encontram (num nó com três vias iguais não dá para saber qual segue); linha de mão única ou de um sentido só junta no
  sentido do trânsito. SP: 280.926 linhas → 155.372 (-45%), 36,8 → 29,2 MB. O teto de 5 km evita uma linha de centenas de km
  que o app teria de ler inteira para casar uma posição.

**Das fontes oficiais.** Rio: o trecho de logradouro da prefeitura (a geometria já vinha na camada que gera os pontos); CET de
São Paulo: a geometria das vias de trânsito rápido (70) e arteriais (50) da classificação viária do GeoSampa; ANTT: a placa vale
da posição dela até a próxima do mesmo sentido (máx. 10 km), como nos pontos, e a rota do SNV é cortada onde qualquer
trecho começa ou termina: valor igual nos dois sentidos dá uma linha sem sentido, diferente (ou um sentido só) dá uma linha por
sentido, desenhada no sentido do trânsito (crescente do km = como o SNV está desenhado, decrescente = ao contrário), com
`direction_deg` = rumo médio. Pontos e linhas de cada fonte saem da mesma leitura (`rio._segments`, `cet_sp._classified_features`
guardam as respostas na execução; a ANTT baixa o KMZ duas vezes). As linhas oficiais têm cópia guardada própria
(`Rio trechos (linhas)`, `CET-SP limites (linhas)`, `ANTT placas (trechos)` em `data/raw/fontes/`); sem cópia e sem a fonte, a falha
vira aviso (não barra o `publish.py`) e o estado sai só com as linhas do OSM, sem corte. Não há reserva pela edição publicada
(ela só tem os pontos oficiais).

**Corte do OSM pelo oficial** (`limit_lines.cut`), no espírito do `override_limits`: cada linha do OSM é medida a cada 20 m, e o
ponto fica de fora se há uma amostra de um trecho oficial a até 50 m (o mesmo raio dos pontos) **e** de orientação compatível
(rumos até 30° de diferença, módulo 180°: uma rua que cruza a via oficial não é cortada). Oficial sem sentido (Rio, CET) cobre
qualquer sentido; oficial de um sentido só (ANTT) cobre a via de mão única do mesmo sentido, e a de mão dupla só quando
os dois sentidos têm trecho oficial ali (como nos pontos: com placa de um sentido só, o OSM fica). As sequências de pontos
sem cobertura viram linhas novas (simplificadas a 1 m); sobra com menos de 40 m sai. Medido em SP (155.372 linhas do OSM, 110.000
km) com as linhas oficiais de SP (11.830: ANTT 1.157 + CET 10.673):

| Oficial | raio / ângulo | OSM tocado | cortadas | inteiras fora | km antes → depois |
|---|---|---|---|---|---|
| ANTT | 50 m / 30° | 9.845 | 2.388 | 1.603 | 5.809 → 3.837 |
| ANTT | 25 m / 30° | 9.845 | 1.769 | 937 | 5.809 → 4.226 |
| ANTT | 50 m / 90° (sem orientação) | 9.845 | 3.193 | 2.118 | 5.809 → 3.767 |
| CET | 50 m / 30° | 16.202 | 7.538 | 6.054 | 6.025 → 3.407 |
| CET | 25 m / 30° | 16.202 | 6.782 | 5.559 | 6.025 → 3.526 |
| CET | 50 m / 90° | 16.202 | 9.776 | 7.069 | 6.025 → 3.219 |
| ANTT + CET | 50 m / 30° (o do build) | 23.961 | 9.786 | 7.593 | 10.929 → 6.399 |

Escolhido 50 m / 30°: o raio dos pontos, e a orientação evita cortar a rua transversal e a paralela que cruza (a 90° o corte
passa a levar também as transversais). Dos 10.929 km de OSM tocados em SP, o corte tira 4.530 km, e a CET leva a maior parte porque a classificação viária cobre as avenidas e o OSM as desenha em duas pistas (duas linhas de mão única por
linha oficial). No Brasil (lido com as linhas oficiais da ANTT e da CET; as do Rio ficaram de fora, ver abaixo): 46.965 km
de OSM tocados → 28.553 km. O Rio não foi medido: o servidor da prefeitura (`pgeo3`) respondeu com erro e timeout durante a
medição de 2026-11-08, e RJ saiu sem corte pelo Rio. A medição do corte do Rio fica para o build.

**Tamanho** (CSV; medido sem build, chamando `osm_pbf.load` nos cinco extratos de 2026-11-08 e as funções do pacote; os pontos
são só os do OSM, sem os oficiais, então o `limites.csv` real é um pouco maior):

| UF | linhas | `limites_trechos.csv` | linhas estimadas | pontos do OSM (`limites.csv`) |
|---|---|---|---|---|
| SP | 159.701 | 29,0 MB | 80.871 | 16,4 MB |
| MG | 93.197 | 30,6 MB | 46.480 | 15,1 MB |
| RS | 54.562 | 13,5 MB | 27.472 | 8,2 MB |
| PR | 48.808 | 11,7 MB | 22.199 | 6,9 MB |
| BA | 34.403 | 13,3 MB | 25.309 | 7,8 MB |
| RJ | 25.846 | 6,7 MB | 14.813 | 3,4 MB |
| GO | 29.804 | 6,3 MB | 19.383 | 4,5 MB |
| Brasil (27 UFs) | 663.631 | 171,9 MB | 359.672 | 101,0 MB |

O maior arquivo é o de MG, com 30,6 MB (teto de 95 MB). Os trechos pesam cerca de 1,7 vez os pontos (a geometria são ~1,1 milhão
de vértices só em SP). Não há versão em `brasil/`: a soma, 172 MB, passaria do teto, e o app baixa o estado. Metade das linhas
é estimada (`estimated=1`): se o arquivo pesar demais para o app, a coluna deixa filtrar. Tempo (nesta máquina): a passada
do OSM com as linhas levou 145 s para o recorte de SP, 188 s para o sudeste inteiro, 4,3 GB de memória no pico; juntar e
cortar leva segundos por estado.

**Fora do escopo.** Os limites oficiais de outros órgãos (DER-SP, Goinfra) vêm como pontos, sem geometria de trecho; vias sem
`maxspeed` e fora da rede principal (residencial, serviço, estrada sem classe) continuam sem linha nem estimativa, como nos
pontos. Uma via do OSM de mão dupla com oficial de um sentido só fica inteira (nos dois sentidos).

### Câmeras de fiscalização sem velocidade (2026-11-08)

`estados/<UF>/cameras_fiscalizacao.csv` (pacote no schema 11): `lat,lng,kind,source,active`. O CET de São Paulo, a BHTrans e a
Setran de Curitiba listam locais de câmeras que fiscalizam outras infrações; o gerador as descartava (`cet_sp._enforces`: só V e
A; `bh._kind`; `municipal.parse_curitiba`). Agora vão para um arquivo à parte, para não misturar com radar de velocidade. O
`radares.csv` não mudou. O mesmo local pode estar nos dois: dos 615 locais do CET com outra infração, 610 também são radar de
velocidade ou de avanço de sinal.

**Códigos do CET** (tabela `Enquadramentos` do mesmo relatório Power BI, com a legenda de cada código, lida em 2026-11-08; o
dicionário do CSV do GitHub manda consultar essa tabela): V velocidade e A avanço de sinal (radares.csv); `EXD`/`EXE` faixa
exclusiva (direita/esquerda) → `BUS_LANE`; `CPD`/`CPE` conversão proibida (direita/esquerda) → `NO_TURN`; `P` parada sobre a
faixa de pedestres → `STOP_ON_CROSSWALK`; `R` rodízio → `ROAD_ROTATION`; `Z` (ZMRC), `VR` (VER) e `PR` (faixa proibida,
caminhão à esquerda) → `TRUCK_RESTRICTION`; `F` (ZMRF, fretados) → `CHARTER_RESTRICTION`; `MT` motocicletas →
`MOTORCYCLE_RESTRICTION`; `S` trânsito seletivo → `OTHER` (2 locais). Todo código da base tinha legenda; um código novo cai em
`OTHER`.

**BHTrans** (tipo do controlador): conversão-retorno em local proibido → `NO_TURN`, invasão de faixa exclusiva (MOVE) →
`BUS_LANE`. **Curitiba** (títulos dos ícones da página da Setran): Parada na faixa → `STOP_ON_CROSSWALK`, Conversão proibida →
`NO_TURN`, Retorno proibido → `NO_U_TURN`, Conversão obrigatória → `MANDATORY_TURN`, Faixa Exclusiva → `BUS_LANE`, Peso Bruto Total
→ `TRUCK_RESTRICTION`.

**Escolhas.** Uma linha por local e infração, não uma lista com `;` (o app filtra por `kind` e liga/desliga o grupo; um local
com cinco infrações vira cinco linhas de ~45 bytes, e conversão à direita e à esquerda são uma linha só). Só locais em operação
(`active` é sempre `1`; a coluna fica por simetria com o `radares.csv`): os 1.195 locais desativados do CET não ajudam um app de
alerta. `source` com código próprio (`CET-SP:CAM`, `BHTRANS:CAM`, `CURITIBA:CAM`): a reserva pela edição publicada procura radares
no `brasil/radares.csv` pelas partes da coluna `source`, e com o código do radar essas câmeras voltariam como radar.

**Onde passam.** Ficam fora do `SourceData.cameras` das três fontes (ali viram radar na mescla, entram na trava de queda do
`publish.py` e na cópia guardada da fonte). `BuildContext.enforcement_cameras` as lê à parte, depois de `official()`: o CET
reaproveita a tabela que a leitura dos radares guardou em `data/raw/cet_sp_locais.json` (sem segunda consulta ao Power BI),
a BHTrans e a Setran leem o CSV e a página uma vez só por execução (`bh._csv_text`, `municipal._curitiba_html`) para os
radares e para as câmeras. Cada fonte tem cópia guardada própria (`CET-SP (outras câmeras)`, `BHTRANS (outras câmeras)`,
`Curitiba (outras câmeras)`); sem cópia, a falha vira aviso, não falha (o arquivo não tem reserva pela edição). Só as fontes
ligadas no build são lidas.

**Contagens** (2026-11-08): CET de São Paulo 615 locais ativos, 1.306 linhas (`ROAD_ROTATION` 388, `TRUCK_RESTRICTION` 384,
`CHARTER_RESTRICTION` 174, `STOP_ON_CROSSWALK` 170, `BUS_LANE` 158, `MOTORCYCLE_RESTRICTION` 19, `NO_TURN` 11, `OTHER` 2); BHTrans
(MG) 51 locais (`NO_TURN` 28, `BUS_LANE` 23); Curitiba (PR) 234 locais, 320 linhas (`STOP_ON_CROSSWALK` 223, `NO_TURN` 44,
`NO_U_TURN` 20, `MANDATORY_TURN` 17, `BUS_LANE` 12, `TRUCK_RESTRICTION` 4). Total: 1.677 linhas, 900 locais. O Rio publica
em PDF seções de faixa exclusiva, carga e conversão sem coordenada (`rio.parse_list` as descarta); não entram.

### Contornos das UFs (2026-11-08)

`brasil/ufs.geojson` e a chave `ufs_geojson` do `catalogo.json` (`datakit/build_ufs.py`): uma feição por UF (`uf`, `name`) com a
malha oficial do IBGE já usada no recorte, simplificada (shapely, `simplify(tol, preserve_topology=True)`) e com quatro casas. Medido
nas 27 UFs: contorno cheio 1.001 KB; tolerância 0,002° → 836 KB; 0,005° → 457 KB; 0,01° → 250 KB; 0,02° → 132 KB. Casas decimais
(4 ou 5) não mudaram o tamanho. Escolhida a 0,02° (132,9 KB; alvo ≤ ~150 KB). Erro: o maior desvio de um vértice do contorno
original para o simplificado é de 3,0 km (no Pará; a tolerância é de 0,02°, ~2,2 km, e a preservação da topologia passa um pouco
dela); no sentido inverso, 0,1 m. É para o app escolher os pacotes pela posição, não para decidir a divisa: perto dela (uns 5 km) o
app deve olhar também os estados vizinhos. Sem `shapely` ou sem a malha, o arquivo não sai.

## Sentido dos radares e das placas (2026-09-29)

`direction_deg` em radares e limites: rumo do trânsito fiscalizado (graus a partir do norte),
vazio = os dois sentidos ou desconhecido. Como cada fonte informa o sentido e como vira rumo:

| Fonte | Campo | Conversão para rumo | Medição |
|---|---|---|---|
| ANTT — Radar | `sentido` Crescente/Decrescente (+ `rodovia`, `uf`) | Rota do SNV da BR: direção em que o km cresce no ponto (±50 m), +180° no decrescente | km da ANTT cresce no mesmo sentido do SNV em todas as concessões; lado da pista confirma o sentido em 96% dos radares a 25-80 m do eixo |
| DNIT — PNCV | `Faixas` (`P-C-n` crescente, `P-D-n` decrescente) | Idem, SNV | 927 de 1.774 com um sentido só; lado da pista confirma em 95-100% a > 15 m do eixo |
| DER-GO | `SENTIDO`, `SRE`, `COMPLEMENT` (km) | Malha estadual da Goinfra (`MalhaEstadual_gdb`): trechos por SRE com km inicial/final, km de cada vértice pelo comprimento | Trecho desenhado do km inicial ao final em 1.002 de 1.010 radares; km do radar a 4 m da posição (mediana); lado da pista confirma em 94-100% a > 15 m |
| Artesp (concessões SP) | `Sentido` Norte/Sul/Leste/Oeste (nominal da rodovia) | Só com o radar claramente sobre uma pista de mão única do OSM (a pista do outro sentido 6 m ou mais além), e o nominal não pode contrariar essa pista; em via de mão dupla, vazio (ver a conferência abaixo) | — |
| DER-SP (rede própria) | `Faixas` (`N-1`, `S-1`, `L-1`, `O-1`) | Idem Artesp; "N-1, S-1" = os dois sentidos | Ver "Conferência do sentido em SP" abaixo |
| CET-SP (radares da capital) | Descrição "(CENTRO/BAIRRO)" ou "(BAIRRO/CENTRO)"; pares de lugares ("RAPOSO/MARGINAL") sem sentido utilizável | Mesma regra da Artesp: sentido da pista de mão única em que o radar está; centro/bairro (rumo que se afasta ou se aproxima do marco zero) só confere. Com par de lugares, vale a pista sozinha | Ver a conferência abaixo |
| OpenStreetMap | `direction` do radar | **Não usado** (`osm_pbf.USE_OSM_DIRECTION = False`). Código pronto: graus e pontos cardeais direto; `forward`/`backward` pela direção do way no nó | 1.587 dos 9.888 radares do OSM têm `direction`. Nas BRs (radar a > 15 m do eixo) o lado da pista confirma o sentido em só 38% dos 88 casos (DNIT 97%, ANTT 89%, DER-GO 90%, DER-SP 78%); a < 40 m de um radar oficial com sentido, 1 em cada 3 aponta o contrário. Muitos mapeadores marcam para onde a câmera olha |
| ANTT — Sinalização (placas) | `sentido` Crescente/Decrescente | SNV, como os radares | Por km de rodovia: 4.845 km com o mesmo limite nos dois sentidos (ponto sem sentido), 3.690 km com limites diferentes (antes descartados; agora um ponto por sentido), 1.871 km com placa de um sentido só (antes valia para os dois; agora só para o sentido dela) |

A medição do "lado da pista": no Brasil se anda pela direita, então num trecho de pista dupla
o radar do sentido crescente fica à direita do eixo (olhando para onde o km cresce). Perto do
eixo (< 15 m) o próprio eixo do SNV/Goinfra é impreciso e a concordância cai para 63-86%; com o
radar claramente numa das pistas ela sobe para 94-100%, o que mostra que o erro está no eixo,
não no sentido informado. O rumo em si vem da tangente da via e não depende desse deslocamento.

### Conferência do sentido em SP (2026-09-29)

Artesp, DER-SP e CET dão só o sentido nominal, então a conferência usou a posição do radar,
sem olhar o sentido: com o radar claramente sobre uma pista de mão única do OSM (a pista do
outro sentido a 6 m ou mais além), o sentido daquela pista é a referência.

| Fonte | Concordância (radar sobre pista de mão única inequívoca) |
|---|---|
| DER-SP / Artesp | 609 de 701 = 87% |
| CET-SP | 297 de 319 = 93% |

Nos casos em que discordam, a coordenada põe o radar numa pista e o sentido nominal manda para
a outra, e não há como saber qual dos dois erra. Regra adotada (`osm_pbf.resolve_probes`): nesses
casos o radar fica sem sentido (vale para os dois). Depois da regra, a mesma conferência dá
625 de 626 (DER-SP/Artesp) e 295 de 296 (CET) = 100%, com 849 e 373 radares com sentido (75 e 23
ficaram sem sentido pela regra).

Tentativa de conferir o nominal em via de mão dupla pela quilometragem: malha do DER-SP (KMZ do
"Sistema Rodoviário Estadual", trechos com km inicial/final, orientados pela ligação com o trecho
seguinte; o km calculado bate com o impresso no radar em 708 de 738) mais a planilha "Malha
Rodoviária" da Artesp (qual sentido nominal é o crescente em cada trecho). Resultado: 81% de
concordância com a posição em pista de mão única, pior que os 87% do método pela via do OSM;
a geometria está certa, o que erra é o próprio sentido nominal em ~13-19% dos radares. Sem
referência independente para a via de mão dupla, a regra final (`osm_pbf.POSITION_CONFIRMS`)
só publica o sentido confirmado pela posição: sentido errado faz o radar sumir para quem passa,
sentido vazio só avisa nos dois sentidos. Em via de mão dupla não há referência
independente: o lado da via não serve, porque as coordenadas ficam a poucos metros do eixo
(concordância de 46-82%, casos demais perto do eixo para concluir).

### Sentido pelo lado da via de mão dupla: medição (2026-10-07)

Pergunta: dá para dar sentido aos radares que não têm, pelo lado do eixo da via em que o ponto
está? No Brasil se anda pela direita, então numa via de mão dupla o poste à direita do eixo
(olhando num sentido) fiscalizaria aquele sentido. Só medição: nada mudou nos pacotes.

Gabarito: os 3.679 radares dos pacotes de 2026-10-06 que já têm `direction_deg`. Para cada um,
o trecho de via do OSM mais perto (até 40 m; vias de veículo, extratos regionais da Geofabrik
da mesma geração), o lado do eixo e o rumo inferido, contra o sentido conhecido (certo se a
menos de 90°).

- 2.471 têm uma pista de mão única como via mais perto (o caso que `resolve_probes` já cobre;
  conferência: o sentido da pista bate em 2.321, 94%).
- 1.187 ficam numa via de mão dupla: é o caso medido. 18 caíram numa transversal (eixo a mais
  de 45° do sentido) e 3 não têm via a 40 m.

Acerto em via de mão dupla, por distância do ponto ao eixo do OSM:

| Fonte | 0-3 m | 3-6 m | 6-10 m | 10-15 m | 15-25 m | Total |
|---|---|---|---|---|---|---|
| DNIT | 78% (88) | 91% (139) | 90% (147) | 87% (46) | 80% (5) | 88% (426) |
| ANTT | 65% (62) | 80% (88) | 79% (111) | 88% (43) | 67% (9) | 77% (313) |
| DER-GO | 60% (177) | 83% (147) | 90% (89) | 73% (15) | 100% (2) | 75% (433) |
| Todas | 66% (330) | 84% (377) | 86% (350) | 82% (108) | 72% (18) | 79% (1.187) |

Por classe da via: `trunk` 87% (642), `primary` 79% (400), `secondary` 71% (80), `tertiary` 27%
(11), `residential` 17% (30). Rente ao eixo o lado é sorte; em rua de bairro, o ponto mais perto
costuma ser outra rua.

Melhor recorte (escolhido entre ~100, o que infla o número): DNIT em `trunk`/`primary`, de 6 a
15 m do eixo, 171 de 178 = 96,1% (limite inferior de Wilson 95%: 92,1%; metades sorteadas de
94,4% a 98,9%). Concentrado no RS (84 de 84) e SC (25 de 25); no ES, 15 de 19.

Por que não serve: os radares do DNIT sem sentido no pacote **não** são de sentido
desconhecido. Na planilha do PNCV, 973 fiscalizam faixas de um sentido só, 783 fiscalizam
faixas dos dois sentidos (`P-C-n` e `P-D-n`) e 18 não informam; os sem sentido são quase todos
os de dois sentidos, e o vazio está certo (vale para os dois). Dos 870 sem sentido, 275 cairiam
no recorte acima: dar um sentido a eles faria o radar sumir para quem passa no outro. Nas fontes
que não informam sentido nenhum (OSM, Inmetro, Detran-DF, prefeituras), os radares são urbanos,
o gabarito não tem como medi-los, e o que ele mostra em via urbana (`secondary` 71%,
`residential` 17%) fica longe dos 95%.

Recomendação: **não adotar**. O vazio continua significando "os dois sentidos ou
desconhecido". A medição confirma, por um terceiro caminho, que o sentido do DNIT de um sentido
só está certo (88-91% a 3-15 m do eixo, com o erro do eixo do OSM somado).

### CET-SP — radares da capital (2026-09-29)

Fonte: "Locais fiscalizados" da página Fiscalização Eletrônica do Trânsito da CET
(cetsp.com.br), um relatório Power BI público atualizado todo dia, lido pela API pública do
relatório (`sources/_powerbi.py`, tabela `tblFiscalizacaoEletronica`: código do local,
coordenada, descrição, enquadramentos, velocidade, ativação/desativação). 2.125 locais, 931
ativos; 905 fiscalizam velocidade (V, 867, com limite) ou avanço de sinal (A, 38). 627 já
estavam no pacote pelo OSM (a < 30 m), 278 são novos. Os locais só de rodízio, faixa
exclusiva, conversão proibida etc. ficam de fora. Alternativa descartada: o pacote `radarsp` (ciclocidade),
que tem um dicionário de locais de 2024 montado a partir de pedido por LAI; a fonte da CET é
a original e está atualizada.

**Reserva (desde 2026-11-08):** a CET também publica a mesma base em CSV no GitHub
(`github.com/cetsp-dados/dados-fiscalizacao-eletronica`, `Base_Locais_Fiscalizados.csv`, desde
2026-10-27, com dicionário de dados): mesmos campos e nomes, mais número de série, faixas, captura e
redutor; enquadramentos separados por ";" e datas em AAAA-MM-DD. É atualizada à mão (em 2026-11-08:
2.074 locais e a última ativação/desativação em 2026-10-20, contra 2.127 e 2026-11-05 no Power BI).
`cet_sp._rows_with_fallback` lê as duas e usa o CSV só quando o Power BI falha ou quando a data mais
recente de ativação/desativação do CSV é mais nova que a do Power BI (aviso no build nos dois casos);
se as duas falharem, a cópia da última leitura boa em `data/raw/`. O portal de dados abertos da
prefeitura (`dados.prefeitura.sp.gov.br`, conjunto "Fiscalização Eletrônica - Locais Fiscalizados",
CC-BY) tem a mesma base em XLSX/CSV mensal, mas atrasada (a mais nova é de 06/2026): não é usado.

### Auditoria das junções (2026-09-30)

Simulada com os dados de antes das junções (sem a CET), com `data/audit/juncoes_<UF>.csv`:

| Junção | Pares | Distância mediana / p90 | Limites diferentes | Outros |
|---|---|---|---|---|
| Entre órgãos | 11 | 18 / 28 m | 0 | — |
| OSM + OSM (≤ 8 m) | 141 | 6 / 8 m | 1 (1%) | 14 com um lado radar de trecho (vira trecho) |
| OSM + oficial (≤ 30 m) | 1.692 | 14 / 26 m | 61 de 686 (9%; ANTT 23, Detran-DF 13, Rio 8) | 22 pontual x trecho (vira trecho); 15 com situação diferente (oficial inativo: DER-SP cancelado 7, DNIT com aferição vencida 7) |

Os pares com limite diferente estão à mesma distância que os outros (mediana 18 m): é o mesmo
equipamento com limite divergente entre as fontes; vale o oficial. Situação diferente: vale o
oficial (mesma lógica dos desativados da CET). As regras ficam como estão.

Busca de vizinhos (2026-09-30): as junções usavam uma grade de células quadradas em graus e só
olhavam as 8 células em volta; como o grau de longitude encolhe com a latitude, pares a
leste-oeste perto do raio escapavam (em teste sintético com o ponto na borda da célula, desde
23° S). Agora `datakit/common/spatial.py` abre as células que cobrem o raio nos dois eixos; o
mesmo valeu para a margem da sonda de sentido no OSM e para a caixa das linhas com km (SNV, malha
do DER-GO). Refeitas as junções sobre os radares já publicados, apareceram só 4 pares a mais
(OSM + oficial em DF, PI e SP; OSM + OSM no RS): o efeito era raro, mas não mais.

### Em que UF fica cada ponto (2026-09-30)

Antes cada UF recortava as listas pelo próprio polígono (malha simplificada do IBGE): o que caía
fora de todos sumia de todos os pacotes — ponte, orla, ilha (os 12 radares da ANTT na Ponte
Rio-Niterói, a até ~2,8 km do polígono do RJ) — e o que caía em dois polígonos sobrepostos saía
nos dois. Agora `datakit/common/ufassign.py` decide uma vez por ponto: o polígono que contém; se
nenhum, a UF mais perto a até 5 km; se nada a 5 km, nenhuma. Ponte/túnel fica com a UF de
qualquer uma das pontas. Sobre a linha de base (2,86 milhões de pontos, 0,9 s): só 24 pontos de
limite mudam, os que saíam em PE e PB ao mesmo tempo (ficam na PB). Os pontos que estavam fora
de todos os polígonos só aparecem no próximo build.

Build de conferência (GO, RJ e SC, mesmos extratos do OSM) contra o build anterior: GO sai com
os mesmos radares e estruturas; o RJ ganha os 12 radares da ponte (9 posições; 4 juntados ao OSM)
e 6 radares do OSM na orla, 1.731 pontos de limite fora de todo polígono (Rio 1.365, ANTT 86 na
ponte, OSM no resto) e 88 pontes/túneis; SC ganha 175 limites e 3 estruturas na orla/ilha. Saem
7 limites do OSM no RJ e 3 em SC, agora cobertos por um limite oficial a até 50 m. Os pacotes
passaram a sair direto da memória (sem os tiles intermediários); a volta pelos tiles arredondava
as coordenadas e juntava por acaso alguns pontos de limite a ~1 m um do outro (10 nos 3 estados),
que agora ficam os dois.

### Radar de órgão estadual ou municipal fora da UF do órgão (2026-10-01)

Nos dados publicados em 01/10/2026 (17.800 radares; 6.983 de órgão estadual, distrital ou
municipal), 4 estavam numa UF que não é a do órgão. Distância até o polígono da UF do órgão:

| Fonte | Caiu em | Coordenada | Distância da UF do órgão |
|---|---|---|---|
| DETRAN-DF | GO | -15.58148, -47.34271 | 0,1 km |
| DER-SP | MG | -22.26290, -46.59110 | 10,0 km |
| DER-SP | PR | -23.18713, -49.96888 | 16,0 km |
| DER-SP | SC | -27.88159, -50.65344 | 380,1 km |

Órgão estadual não fiscaliza a 10 km para dentro do estado vizinho: os três do DER-SP são
coordenada errada na fonte. Regra (`_drop_far_from_home` em `datakit/build.py`): radar de órgão
de outra UF fica se estiver a até 5 km da UF do órgão (a mesma folga da divisa); mais longe, sai,
e o build registra no log. Fontes federais e o OSM não entram na regra.

O campo `coverage.level` do catálogo contava esses radares: SC, PR e MG saíam com cobertura
estadual por causa de um radar do DER-SP cada, e o DF saía só como "federal" porque o Detran-DF
não era contado. Agora o nível só conta órgão da própria UF, e o Detran-DF conta como estadual.

### Endereços do Inmetro geocodificados pelo CNEFE do IBGE (2026-10-01)

O CNEFE do Censo 2022 (`ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/
Censo_Demografico_2022/Arquivos_CNEFE/CSV/`, um CSV por UF e um por município) traz, para cada
um dos 106,8 milhões de endereços do país, tipo, título e nome do logradouro, número, latitude,
longitude e o nível da coordenada (`NV_GEO_COORD`: 1 e 2 são do próprio endereço). É o
geocodificador nacional com número de porta que faltava. Licença específica do CNEFE não
confirmada (dado público do IBGE, como a malha das UFs já usada).

Medidores fixos e válidos do Inmetro só com endereço, no país: 7.311 locais distintos. Como o
endereço vem escrito:

| Forma | Locais | |
|---|---|---|
| Rua + número ("AV. CABO BRANCO, Nº 2300") | 3.054 | 41% |
| Cruzamento ("AV. T 7 X AV. CASTELO BRANCO") | 1.849 | 25% |
| Setor de Brasília ("VIA M2 QNM 20") | 260 | 3% |
| Quadra e lote (quase só Goiás) | 142 | 1% |
| "A 23 m da rua tal" | 108 | 1% |
| Outro (ponto de referência, "em frente a…") | 1.898 | 25% |

Goiás é atípico (707 locais: 260 de Brasília, 166 cruzamentos, 130 quadra/lote, só 78 com
número); SP tem 2.572 locais, 1.265 com número.

Medição em quatro capitais que têm lista oficial com coordenada, para ter com o que comparar.
Rua + número: o nome da rua é normalizado (sem acento, abreviaturas expandidas, sem o tipo do
logradouro) e procurado no CNEFE do município (igual, ou parecido com o mesmo último nome); o
ponto é o do número mais próximo na rua, interpolando entre o menor e o maior. Cruzamento: o par
de endereços mais próximos entre as duas ruas, se ficarem a até 80 m um do outro. Distância do
ponto obtido até o radar publicado mais perto (qualquer fonte):

| Cidade | Locais | Rua + número, com número a até 20 de um endereço do CNEFE | Cruzamento |
|---|---|---|---|
| Belo Horizonte | 119 | 56: mediana 26 m, 80% a ≤ 50 m, 92% a ≤ 100 m | 4: mediana 72 m |
| Fortaleza | 106 | 54: mediana 25 m, 61% a ≤ 50 m, 77% a ≤ 100 m | 26: mediana 32 m, 73% a ≤ 50 m, 88% a ≤ 100 m |
| Recife | 71 | 16: mediana 22 m, 62% a ≤ 50 m, 87% a ≤ 100 m | — |
| João Pessoa | 74 | 26: mediana 14 m, 84% a ≤ 50 m, 88% a ≤ 100 m | 17: mediana 26 m, 82% a ≤ 50 m |
| Soma | 370 | 152: 72% a ≤ 50 m, 86% a ≤ 100 m, 91% a ≤ 200 m | 47: 72% a ≤ 50 m, 85% a ≤ 100 m |

Funil nas quatro: dos 370 locais, 220 têm número; a rua foi achada em 200 (91%; 188 com o nome
igual); em 152 há endereço no CNEFE com número a até 20 do procurado. Sem esse filtro (os 200):
57% a ≤ 50 m e 75% a ≤ 100 m. Dos 64 cruzamentos, as duas ruas foram achadas em 53 e ficam a até
80 m em 47.

Leitura: a distância mede o erro por baixo, porque parte dos locais do Inmetro não está em lista
nenhuma (o que sobra a mais de 200 m pode ser radar que falta na base, não erro). Mesmo assim é
outra ordem de precisão em relação ao "rodovia + km" medido antes (SNV: mediana 226 m, 34% a
≤ 100 m): aqui a mediana fica entre 14 e 32 m. **Não medido:** cidades sem lista oficial, onde
não há com o que comparar, e as formas de Goiás e de Brasília (quadra/lote e setor).

**Virou fonte do gerador** (`datakit/inmetro_addresses.py`, `sources/cnefe.py`,
`common/address.py`). Regra: o ponto do endereço nunca move um radar conhecido. A até 100 m de um
radar de velocidade (ativo antes de inativo), só o confirma: a fonte ganha `+INMETRO` e o limite
é preenchido se faltava; radar inativo de fonte sem situação própria (OSM, DNIT, DER-GO,
Detran-DF) volta a ativo. Longe de todos, vira radar novo com fonte `INMETRO`; dois locais do
Inmetro a até 30 m um do outro são um só.

País inteiro, sobre os 17.800 radares publicados em 01/10/2026:

| | |
|---|---|
| Locais com "rua + número" ou cruzamento | 4.693 |
| Localizados pelo CNEFE | 2.938 (2.111 pelo número, 827 pelo cruzamento) |
| Radares conhecidos confirmados | 835 (50 ganharam limite, 1 voltou a ativo) |
| Radares novos | 1.714 (1.397 com limite), em 197 municípios |

Por UF, os novos: SP 678, PR 197, SC 164, MG 143, RS 123, GO 82, MS 54, MT 54, CE 35, BA 33, PA
23, PB 16, PE 16, TO 14, RJ 13, PI 12, RO 12, RN 10, AP 9, AM 8, MA 7, RR 6, ES 5; nenhum em AC,
AL, DF e SE. Cidades com mais: Joinville 102, Maringá 63, Guarulhos 63, Taubaté 42, Campinas 38,
Cascavel 37, Jacareí 34, Jundiaí 31. O DF fica de fora porque os endereços de Brasília são por
setor, forma que o leitor não trata.

Conferência com a fonte já integrada, nas cinco cidades com lista oficial completa (São Paulo,
que não entrou na medição acima, e as quatro de antes): 483 locais localizados, mediana de 23 m
até o radar publicado mais perto, 89% a ≤ 100 m, 6% entre 100 e 300 m, 4% a mais de 300 m. Ou
seja, nessas cidades cerca de 1 em cada 10 locais viraria "radar novo" sem que a lista oficial o
confirme: é o tamanho do erro esperado entre os novos. No resto do país (2.432 locais) a
distribuição tem dois grupos: 23% a ≤ 100 m de um radar conhecido, 5% entre 100 e 300 m e 71% a
mais de 300 m. Erro de posição encheria a faixa do meio; o grupo de longe é radar que a base
não tinha.

A conferência em São Paulo achou um erro do leitor de endereços, corrigido: a vírgula de um
decimal ("A MAIS 24,7 METROS DO NUMERO 966") e uma distância ("2 METROS APÓS A AV. …") eram lidas
como número de porta e punham o radar no número 5 ou 7 da avenida, a centenas de metros.

Custo: o cadastro de 295 municípios soma 1,1 GB e é baixado uma vez (o Censo não muda); com os
arquivos em `data/raw/cnefe/`, a geocodificação do país leva cerca de 2 minutos.

### Build depois da revisão do gerador (2026-09-30)

Build completo (27 UFs, mesmos extratos do OSM) contra o anterior: 0 falhas; radares 17.748 →
17.798, limites 2.844.362 → 2.861.115, estruturas 127.107 → 127.467; nenhuma UF caiu mais de 5%.
Diferenças: pontos na ponte/orla/ilha fora do polígono antigo que antes sumiam (47 radares, 8.491
limites, 342 estruturas); troca de UF na divisa pela malha oficial do IBGE (7 radares, 1.826
limites, 100 estruturas, quase todos a < 5 km da divisa); limites do OSM com sentido (3.524
pontos); radares com a situação do próprio órgão em vez da do Inmetro (BHTRANS+OSM,
DNIT+ANTT); um radar do OSM a 29,7 m de um oficial, antes não achado, juntado; e pares de pontos
a ~1 m que o arredondamento intermediário juntava por acaso. Junções auditadas: OSM + oficial
2.460 (mediana 13 m, 76 com limite diferente), OSM + OSM 150, entre órgãos 42.

### Limite por sentido no OSM (2026-09-30)

Vias com `maxspeed:forward` / `maxspeed:backward` (placa diferente em cada sentido), medidas nos 5
extratos: 2.218 ways (814 km), quase tudo no Sul (1.854 ways, 618 km). 1.958 deles (689 km) não
têm `maxspeed` — saíam com o limite estimado pela classe (670 km) ou sem limite (19 km); em 1.523
os dois sentidos têm valores diferentes. Outros 223 (85 km) têm `maxspeed` e um sentido diferente.
Agora saem pontos com `direction_deg` pelo rumo do way (forward = sentido do desenho, backward =
o contrário; o lado sem tag própria fica com o `maxspeed`). Mesmo valor nos dois sentidos = limite
comum, sem sentido. Um sentido só sinalizado e sem `maxspeed`: o outro continua com a estimativa.

### Malha das UFs: a oficial do IBGE (2026-09-30)

A malha vinha de um espelho no GitHub (geodata-br-states). Comparada com a API de malhas do IBGE
(v3, `intrarregiao=UF`):

| Malha | Tamanho | Vértices | Sobreposição entre UFs | Radares ANTT fora de todo polígono | Radares de órgão estadual/municipal fora da UF do órgão (6.981) |
|---|---|---|---|---|---|
| Espelho (antiga) | 5,6 MB | 137.335 | PE × PB | 12 | 5 |
| IBGE intermediária | 0,25 MB | 12.933 | nenhuma | 13 | 7 |
| **IBGE máxima** (adotada) | 1,0 MB | 51.981 | nenhuma | 8 | 4 |

Os 3 radares do DER-SP que caem em SC, PR e MG estão fora de SP em qualquer malha (coordenada da
fonte). Com a máxima, 1.878 dos 2,86 milhões de pontos publicados mudam de UF, todos na divisa
(PR/SC, PE/PB, BA/TO, MG/ES, MT/RO, DF/GO…); a área de cada UF muda menos de 0,7%.

### Radar repetido entre OSM e fonte oficial (2026-09-29)

A mescla por coordenada (5 casas, ~1 m) deixava passar o mesmo radar mapeado no OSM e publicado
por um órgão: 2.502 dos 10.420 radares do OSM ficavam a até 30 m de um oficial (CET-SP 812,
DNIT 488, DER-SP 451, ANTT 336, Fortaleza 243, BH 211...) e saíam em dobro no CSV/GPX/KML.
`model.absorb_osm` junta cada um ao oficial compatível mais perto (ativo antes de inativo; avanço
de sinal só com avanço de sinal; sentidos opostos não), herdando do OSM só o limite que falte e
o fim do trecho. Oficiais não se juntam entre si (radares de um e de outro sentido no mesmo km).

Outras junções (`model.merge_cross_agency`, `model.collapse_osm`): o mesmo radar publicado por
dois órgãos (11 pares a <= 30 m: Detran-DF/DNIT 10, ANTT/DNIT 1) vira um, com a posição de quem
tem sentido; dois radares do OSM a <= 8 m (278 pares) viram um. De 8 a 30 m, os ~1.550 pares do
OSM e os ~560 do mesmo órgão ficam: são quase sempre um equipamento por pista, por faixa ou por
aproximação de cruzamento. A coluna `source` junta as fontes com `+` (ex. `DNIT+OSM`).

Qual posição fica (medido nos 1.695 pares, contra o eixo das malhas oficiais com km: SNV,
Goinfra, DER-SP): ao longo da via as duas diferem pouco (mediana 9-13 m, p75 ~20 m; irrelevante
para o aviso, que começa centenas de metros antes). Para o lado da pista, a oficial é melhor: cerca
de metade dos radares do OSM está desenhada sobre a própria via (< 4 m do eixo: DNIT 53%, ANTT 47%,
DER-GO 55%, contra 23-32% dos oficiais), e, com sentido conhecido, a posição oficial fica do lado
certo da pista em 64% (DNIT, ANTT) e 59% (DER-GO), com 11-14% do lado errado; o OSM, 36-44%. No
DER-SP as duas empatam (54% x 50%). Por isso fica a posição oficial.

Limites do DER-DF (`Rodovias_2025`, campo `velocidade_max`, DERGeo): não usados. É um valor por
trecho inteiro de rodovia (geralmente o limite geral da via); onde já havia limite sinalizado a até
30 m, concorda em só 311 de 876 pontos (35%).

A CET também lista os locais desativados: radar do OSM a até 20 m de um deles, sem local ativo
a 30 m, fica `active=0` (`model.deactivate_near`); medido: 13 a 22 casos, quase todos
desativados em 2023-2024.

Sem sentido publicado: Rio (SMTR), BH, Detran-DF, DER-PE, Fortaleza, Recife, João Pessoa e os
limites do Rio e da CET-SP (trechos de rua, valem para os dois sentidos).
