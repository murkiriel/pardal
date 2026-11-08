# Gerador do Pardal

Código que gera os arquivos deste repositório (`brasil/`, `estados/` e `catalogo.json`) a
partir das fontes abertas listadas no README principal.

## Requisitos

- Python 3.10+ (testado com 3.12) e o binário `curl` no PATH (a PBH barra o TLS do Python, o curl passa)
- `pip install -r requirements.txt` (pyosmium, requests, openpyxl, shapely, pyshp, pypdf, nas
  versões testadas)
- ~2 GB de disco para os extratos do OpenStreetMap e cerca de 1 h de processamento

## Como rodar

Da pasta `gerador/`:

```
python run.py datakit.build --all        # baixa as fontes e gera data/dist/ (27 UFs + Brasil)
python run.py datakit.build --uf GO      # só um estado
python scripts/publish.py               # monta brasil/, estados/ e catalogo.json na raiz do repositório
python -m unittest discover -s datakit/tests -t .
```

Verificação de estilo e de tipos (ferramentas em `requirements-dev.txt`, configuração em
`ruff.toml` e `mypy.ini`):

```
pip install -r requirements-dev.txt
python -m ruff check datakit scripts run.py
python -m mypy datakit scripts
```

Os testes e essas duas verificações rodam também no GitHub a cada push que mexe no código
(`.github/workflows/testes.yml`).

`build --all` já gera os radares em GeoJSON, KML e GPX; para gerá-los de novo sobre um
`data/dist/` existente: `python run.py datakit.build_formats`. Limites e estruturas saem só em
CSV; o `scripts/to_geojson.py` (na raiz do repositório) converte qualquer um para GeoJSON (testado em
`datakit/tests/test_to_geojson.py`).

Os extratos do OSM ficam em `data/raw/`. A cada build o gerador confere na Geofabrik se há
versão mais nova e só então baixa de novo; `--osm-local` usa os guardados sem conferir (útil
para repetir um build com os mesmos dados). Se o link `<região>-latest.osm.pbf` falhar, o
gerador usa o `<região>-AAMMDD.osm.pbf` mais recente da listagem da Geofabrik e registra um
aviso (é o mesmo arquivo; não bloqueia a publicação).

## Como funciona

| Módulo | Papel |
|---|---|
| `datakit/build.py` | Orquestra: fontes → mescla → UF de cada ponto → pacote por UF → catálogo → Brasil → formatos |
| `datakit/context.py` | O estado de uma execução (OSM da região, fontes oficiais, SNV, Inmetro, malha das UFs) e o contrato das fontes: cada fonte oficial expõe `fetch(ctx) -> SourceData` (radares, limites, locais desativados). As câmeras de fiscalização sem velocidade (CET, BHTrans, Curitiba) e os trechos oficiais de limite não passam pelo `SourceData`: têm leitura e cópia guardada próprias (`enforcement_cameras`, `national`) |
| `datakit/sources/` | Uma fonte por arquivo (OSM, DNIT, ANTT, placas ANTT, Inmetro, SNV, DERs, AGETO-TO, Detran-MA, SEINFRA-BA, Rio, BH, Detran-DF, capitais, EPTC de Porto Alegre, Transalvador, SEMTRAN de Porto Velho, CNEFE do IBGE) |
| `datakit/common/model.py` | Formato das linhas e a mescla: radar do OSM a até 30 m de um oficial compatível vira um só (o oficial); radar do OSM num local desativado pela CET fica inativo; limite oficial tira o do OSM a < 50 m (placa de um sentido só tira o do OSM só quando há placa dos dois sentidos) |
| `datakit/common/lrs.py` | Quilometragem das BRs pelas rotas do SNV (DNIT) e de linhas com km só nas pontas (malha da Goinfra) |
| `datakit/common/direction.py` | Sentido dos radares e das placas: "crescente/decrescente" (ANTT, DNIT, DER-GO) vira rumo pela geometria com km; o sentido nominal de SP (Norte/Sul/Leste/Oeste) vira rumo pela via do OSM mais próxima |
| `datakit/inmetro_status.py` | Radar ativo/inativo pela validade da aferição no Inmetro, nas BRs fora de concessão; radar confirmado sem limite (o PNCV do DNIT não traz) ganha a velocidade nominal do medidor; o DER-SP, com situação própria, só o limite, pelo km das planilhas dele |
| `datakit/inmetro_addresses.py` | Medidores do Inmetro que só têm endereço: o ponto vem do cadastro de endereços do IBGE (`sources/cnefe.py`, "rua + número" ou cruzamento; `common/address.py` lê o texto). A até 100 m de um radar conhecido só o confirma (`+INMETRO` na fonte, limite se faltava); longe de todos vira radar novo, fonte `INMETRO` |
| `datakit/build_formats.py` | Radares em GeoJSON, KML e GPX a partir dos CSVs |
| `datakit/limit_lines.py` | Limites como trechos de via (`limites_trechos.csv`): junta as vias contíguas de mesmos atributos, corta do OSM o que um trecho oficial de direção compatível cobre (a até 50 m) e entrega as linhas ao pacote |
| `datakit/build_ufs.py` | `brasil/ufs.geojson`: contorno simplificado de cada UF (malha do IBGE) e a chave `ufs_geojson` do catálogo |
| `scripts/publish.py` | Confere falhas, quedas e tamanhos e copia `data/dist/` (que já tem a estrutura `brasil/`, `estados/`, `catalogo.json`) para a raiz do repositório |
| `datakit/failures.py` | Registro das fontes que falharam na execução |

Cada download tenta 3 vezes quando a falha é passageira (conexão caiu, 5xx), com no máximo 20 s
para abrir a conexão. Um servidor que não abre conexão nem assim é dado como fora do ar pelo resto
da execução (as próximas requisições a ele falham na hora).

Cada fonte atualiza quando dá e, se falhar, fica como estava (`datakit/source_cache.py`): toda
leitura boa é guardada em `data/raw/fontes/<fonte>.pickle`, e quando a fonte falha (portal fora do
ar, mudança de formato, uma base interna da fonte que falhou, ou resultado vazio quando a cópia
tinha dados) o build usa essa cópia, registra um **aviso** (`warnings`, com a data da cópia) e as
outras fontes seguem normalmente. O aviso aparece no build e no `publish.py` mas não bloqueia a
publicação. O mesmo vale para as fontes que guardam arquivos: extratos do OSM, SNV, CNEFE, Inmetro
por UF e radares da CET.

Sem cópia guardada (fonte nunca lida com sucesso naquela máquina, ou cache do Actions apagado), o
último recurso é a **edição publicada** (`datakit/edition.py`): os radares e os limites oficiais que
a fonte tinha em `brasil/radares.csv` e `brasil/limites.csv` (pela coluna `source`; o código é o
nome da fonte no `OFFICIAL`, ou os de `SOURCE_CODES` do módulo). Também vira aviso. O build usa a
raiz deste repositório; `--edition <pasta>` aponta outra e `--no-edition` desliga. Só uma fonte sem
cópia **e** sem linhas na edição (fonte nova no primeiro dia, ou bases que não vão para os CSVs de
radares e limites, como os trechos da PRF) vira **falha**: é pulada, listada no fim do log e no
campo `failures` do `data/dist/catalogo.json`, e o `publish.py` não monta sem `--accept-failures`.

O catálogo publicado tem, em `source_dates`, a data do dado de cada fonte: a do dia em que foi lida
com sucesso, que continua a mesma enquanto ela cai na cópia ou na edição. Passados 60 dias sem
leitura boa, o aviso ganha "ATENÇÃO: dado de N dias" (não bloqueia; a fonte pode ter mudado de
endereço).

Cada build grava `data/audit/juncoes_<UF>.csv` com todos os radares juntados (duplicatas entre
órgãos, OSM com oficial, OSM com OSM): distância, fontes, tipos, limites, sentido e situação dos
dois lados — para conferir as junções.

`python scripts/check_sources.py` testa, em segundos, se cada fonte responde de onde se está
rodando (útil antes de um build em máquina nova ou na nuvem).

Com `--commit`, o `publish.py` põe no commit só `brasil/`, `estados/` e `catalogo.json` —
nunca outras mudanças pendentes no repositório.

O `publish.py` não monta os arquivos se:
- o build ainda está rodando ou caiu no meio (`data/dist/BUILD_EM_ANDAMENTO`, que o build cria
  ao começar e apaga ao terminar; sem opção para passar por cima: rode o build de novo),
- algum arquivo a publicar passa de 95 MB (o GitHub recusa acima de 100 MB; o build já registra
  isso como falha),
- alguma fonte falhou no build (`--accept-failures` para montar assim mesmo), ou
- algum estado perdeu mais de 5% (e pelo menos 50 itens) de radares, limites ou estruturas em
  relação ao `catalogo.json` já publicado (`--accept-drop`).

## Publicação automática

O workflow `.github/workflows/gerar-dados.yml` gera e publica os dados todo dia numa máquina do
GitHub Actions: às 03:17 e às 09:17 em Brasília, confere a data de geração dos dados publicados
(`built_at` do `catalogo.json`) e só gera se ela não for de hoje — se o build falhar ou o GitHub
pular um disparo, o seguinte tenta de novo. Também pode ser disparado à mão (Actions → Gerar
dados → Run workflow; só publica com "publish" marcado; "accept_failures" e "accept_drop" passam
as opções de mesmo nome ao `publish.py`). Roda os testes, o build completo e o
`publish.py --commit --push`, com as mesmas travas: fonte que falhou sem cópia guardada, estado
que perdeu mais de 5% ou arquivo acima de 95 MB fazem o job falhar sem publicar nada. Dia sem
dado novo (só a data do catálogo mudou) não vira commit nem release. O log do build, a auditoria
das junções e o catálogo ficam nos artefatos da execução por 30 dias.

As cópias das fontes (`data/raw/` sem os extratos do OSM) ficam no cache do Actions e são salvas
logo depois do build, mesmo quando o build ou a publicação falham. Com a geração diária o cache é
usado todo dia; o GitHub apaga um cache que fica 7 dias sem uso.

Cada publicação vira também uma **release** (`dados-AAAA-MM-DD`), com a nota das contagens por
estado (e a diferença para a geração anterior) e os anexos `pardal-<UF>.zip`, `pardal-brasil.zip`,
`pardal-brasil-radares.zip`, `catalogo.json` e `SHA256SUMS.txt` (`scripts/release.py`; roda também
à mão depois de um `publish.py --commit`). O link
`https://github.com/Murkiriel/pardal/releases/latest/download/pardal-SP.zip` sempre aponta para a
versão mais recente.

As máquinas do Actions ficam nos EUA, e o DNIT e o Inmetro não aceitam conexão de fora do Brasil
(o portal da ANTT às vezes devolve uma página de bloqueio): o tráfego para esses três servidores,
e só para eles, sai por um túnel WireGuard com saída no Brasil. A configuração do túnel fica no
segredo `MULLVAD_WG_CONF` do repositório (Settings → Secrets and variables → Actions). Se o segredo
faltar ou o túnel não responder (chave revogada, servidor desativado), o job avisa e segue sem
ele: essas três fontes caem nas cópias guardadas. Para consertar, gere outra configuração
WireGuard na conta da Mullvad (servidor no Brasil) e troque o segredo. Testado em 2026-09-30: build completo em ~30 min, mesmos números do build
local.

## Convenções

**Idioma**

- Nomes de arquivos e pastas de dados (publicados e intermediários): português, sem acento, sem
  espaço (`radares.csv`, `limites_estimados.csv`, `estados/GO/`).
- Código: nomes de variáveis, funções, classes, módulos e pastas de código em inglês
  (`publish.py`, `BuildContext`, `merge_cameras`); siglas como são (`dnit`, `cet_sp`, `der_go`).
  Opções de linha de comando também (`--accept-drop`).
- Formato dos dados: colunas dos CSVs, valores (`FIXED`, `BRIDGE`, `OSM:class`) e chaves do JSON
  em inglês.
- Comentários, docstrings, documentação, mensagens de log e de erro, notas das releases, nomes dos
  passos do workflow e mensagens de commit: português.

**Versão do formato (`schema`)**

O `catalogo.json` e o `manifesto.json` de cada pacote têm o campo `schema`, a versão do formato.
Ela sobe quando muda algo que um leitor feito para a versão anterior não entenderia: uma chave
ou coluna renomeada ou removida, um nome ou caminho de arquivo que muda, um valor que muda de
significado. Não sobe quando só entram dados novos, ou chaves e colunas novas que um leitor
antigo pode ignorar. Numa mudança que exige subir a versão, primeiro o gerador passa a escrever
o formato novo junto com o antigo, depois quem lê (o app) passa a usar o novo, e só então o
antigo sai e a versão sobe.

## Mais

- `FONTES.md` — investigação das fontes: o que entrou, o que foi medido e descartado.
- `PENDENCIAS.md` — o que ainda falta e o que destrava cada item.
- Licença do código: MIT (`LICENSE`). Os dados gerados seguem a ODbL 1.0 (ver README da raiz).
