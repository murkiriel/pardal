"""Texto de um PDF baixado (pypdf), página após página. As listas de radar em PDF (Rio, SIE-SC,
AGETO-TO, Detran-MA, SEINFRA-BA, SEMTRAN Porto Velho) são lidas assim."""
from __future__ import annotations

import io


def pdf_text(data: bytes) -> str:
    import pypdf
    return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)


def pdf_layout_text(data: bytes) -> str:
    """Como pdf_text, mas com o texto no desenho da página (`extraction_mode="layout"`): cada linha da tabela
    sai numa linha, com as colunas separadas por espaços. Sem isso o pypdf cola as células ("060EGO0230-16412382
    -5117987960") e não há como separar uma coluna da outra. Lista de equipamentos da GOINFRA (DER-GO)."""
    import pypdf
    return "\n".join(page.extract_text(extraction_mode="layout") or ""
                     for page in pypdf.PdfReader(io.BytesIO(data)).pages)
