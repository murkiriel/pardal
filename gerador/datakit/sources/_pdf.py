"""Texto de um PDF baixado (pypdf), página após página. As listas de radar em PDF (Rio, SIE-SC,
AGETO-TO, Detran-MA, SEINFRA-BA, SEMTRAN Porto Velho) são lidas assim."""
from __future__ import annotations

import io


def pdf_text(data: bytes) -> str:
    import pypdf
    return "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(io.BytesIO(data)).pages)
