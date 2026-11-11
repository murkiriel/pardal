"""Conferência do contrato de catálogo comum v1 (docs/CATALOGO.md), igual nos quatro geradores.

`schema_errors` valida um valor JSON contra o esquema (docs/catalogo-v1.schema.json) sem dependência nova: entende só a
parte do JSON Schema que o esquema usa (type, const, enum, pattern, minimum, minLength, minItems, maxItems, required,
properties, items, $ref local). Palavra-chave que ele não entende é erro, para o esquema não crescer sem a conferência.
`rule_errors` confere o que o esquema não expressa: ids únicos, `requires` e `container` que existem, o bloco do
próprio gerador em `compatibility`, a ordem do bbox e as URLs. Os dois devolvem a lista de problemas (vazia = ok).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA_FILE = "catalogo-v1.schema.json"
SPEC_FILE = "CATALOGO.md"
# O sha256 dos dois documentos, iguais nos quatro repositórios. Mudou um? Mude igual nos quatro e troque o hash aqui,
# neste arquivo, que também é o mesmo nos quatro.
SHARED_DOCS = {
    SPEC_FILE: "9cc03ecc41ee26d1d5140a42f9ea72a977d8d59fcc97ee290f9a8c3033e6ec90",
    SCHEMA_FILE: "c227cc7bc066bcc57940e90e38685fee8ba64f2344c115e939a3b80d0c3678a2",
}

# Os valores conhecidos na versão 1 (listas abertas: um leitor ignora o que não conhece, mas um gerador só escreve estes).
KINDS = {"base", "uf", "uf_light", "national", "resources", "style", "conformance", "auxiliary"}
UNPACK_STEPS = {"gzip", "zstd", "tar", "zip"}
ABIS = {"arm64-v8a", "armeabi-v7a", "x86", "x86_64"}

_KNOWN = {"$schema", "$id", "$defs", "title", "description", "type", "const", "enum", "pattern", "minimum",
          "minLength", "minItems", "maxItems", "required", "properties", "items", "$ref"}
_TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def load_schema(docs: Path) -> Dict[str, Any]:
    return json.loads((docs / SCHEMA_FILE).read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def doc_mismatches(docs: Path) -> Dict[str, str]:
    """{documento: sha256 encontrado} dos documentos compartilhados que não são os esperados (vazio = iguais)."""
    found = {name: file_sha256(docs / name) if (docs / name).exists() else "ausente" for name in SHARED_DOCS}
    return {name: digest for name, digest in found.items() if digest != SHARED_DOCS[name]}


def _is_type(value: Any, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def schema_errors(value: Any, schema: Dict[str, Any], root: Optional[Dict[str, Any]] = None,
                  where: str = "$") -> List[str]:
    root = schema if root is None else root
    unknown = set(schema) - _KNOWN
    if unknown:
        return [f"{where}: palavra-chave do esquema que a conferência não entende: {sorted(unknown)}"]
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            return [f"{where}: $ref não local: {ref}"]
        return schema_errors(value, root["$defs"][ref[len("#/$defs/"):]], root, where)
    errors: List[str] = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, name) for name in names):
            return [f"{where}: {json.dumps(value, ensure_ascii=False)[:60]} não é {'/'.join(names)}"]
    if "const" in schema and value != schema["const"]:
        errors.append(f"{where}: {value!r} deveria ser {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{where}: {value!r} fora de {schema['enum']}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{where}: {value!r} não casa com {schema['pattern']}")
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{where}: texto curto demais")
    if _is_type(value, "number") and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{where}: {value} menor que {schema['minimum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", len(value)):
            errors.append(f"{where}: {len(value)} itens")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += schema_errors(item, schema["items"], root, f"{where}[{i}]")
    if isinstance(value, dict):
        errors += [f"{where}: falta {key}" for key in schema.get("required", []) if key not in value]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += schema_errors(value[key], sub, root, f"{where}.{key}")
    return errors


def _bbox_errors(bbox: Any, where: str) -> List[str]:
    if bbox is None:
        return []
    lat_min, lon_min, lat_max, lon_max = bbox
    errors = []
    if not (-90 <= lat_min < lat_max <= 90):
        errors.append(f"{where}: latitudes {lat_min}, {lat_max} fora de ordem ou de [-90, 90]")
    if not (-180 <= lon_min < lon_max <= 180):
        errors.append(f"{where}: longitudes {lon_min}, {lon_max} fora de ordem ou de [-180, 180]")
    return errors


def rule_errors(catalog: Dict[str, Any]) -> List[str]:
    """As regras do contrato que o esquema não expressa. Supõe o catálogo já válido pelo esquema."""
    contract = catalog["contract"]
    errors: List[str] = []
    dataset = contract["dataset"]
    if dataset not in contract["compatibility"]:
        errors.append(f"compatibility sem o bloco do próprio gerador ({dataset})")
    others = {"carcara", "andorinha", "sabia", "pardal"} - {dataset}
    errors += [f"compatibility com o bloco de outro gerador: {name}" for name in sorted(others & set(contract["compatibility"]))]
    if "build_id" in catalog and catalog["build_id"] != contract["build_id"]:
        errors.append("contract.build_id diferente do build_id do topo")
    if contract["version"] < contract["min_reader_version"]:
        errors.append("min_reader_version maior que version")
    if dataset == "pardal" and not contract["built_at"].startswith(contract["build_id"][:10]):
        errors.append("o build_id do Pardal começa pela data do built_at")
    files = contract["files"]
    ids = [f["id"] for f in files]
    errors += [f"id repetido: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    by_id = {f["id"]: f for f in files}
    for f in files:
        where = f"files[{f['id']}]"
        if f["kind"] not in KINDS:
            errors.append(f"{where}: kind desconhecido na v1: {f['kind']}")
        errors += [f"{where}: passo de unpack desconhecido na v1: {s}" for s in f["unpack"] if s not in UNPACK_STEPS]
        errors += [f"{where}: requires aponta para {r}, que não está no catálogo" for r in f["requires"] if r not in by_id]
        if f["id"] in f["requires"]:
            errors.append(f"{where}: requer a si mesmo")
        errors += _bbox_errors(f["bbox"], where)
        if f["coverage_level"] is not None and f["bbox"] is None:
            errors.append(f"{where}: nível de cobertura sem bbox")
        if (f["region"] is None) != (f["bbox"] is None):
            errors.append(f"{where}: region e bbox têm de ser os dois nulos ou os dois preenchidos")
        if f["kind"] == "base" and f["coverage_level"] != "BASE_HIGHWAYS_ONLY":
            errors.append(f"{where}: a base é BASE_HIGHWAYS_ONLY")
        if f["kind"] in ("uf", "uf_light", "national") and f["coverage_level"] != "DETAILED":
            errors.append(f"{where}: estado e país inteiro são DETAILED")
        if not f["unpack"] and f["bytes_unpacked"] is not None:
            errors.append(f"{where}: bytes_unpacked num arquivo que não se desempacota")
        if ("container" in f) != ("member" in f):
            errors.append(f"{where}: container e member andam juntos")
        if "container" in f:
            box = by_id.get(f["container"])
            if box is None:
                errors.append(f"{where}: container {f['container']} não está no catálogo")
            elif "zip" not in box["unpack"]:
                errors.append(f"{where}: container {f['container']} não é um zip")
    return errors


def problems(catalog: Dict[str, Any], docs: Path) -> List[str]:
    """Esquema primeiro; as regras só fazem sentido num catálogo que passou nele."""
    found = schema_errors(catalog, load_schema(docs))
    return found or rule_errors(catalog)
