"""Genera chunks de los documentos cuyo formato original fue PDF.

La entrada oficial es Fase_1_Limpieza/output final limpio/. El manifiesto de
Fase 1 se usa para conservar doc_id, fuente, fenómeno y la trazabilidad al PDF
original. El contenido puede estar en Markdown (.md) o en TXT (.txt) cuando
Fase 1 tuvo que usar el extractor de respaldo.

Estrategia:
* respeta encabezados, párrafos y listas del Markdown;
* divide únicamente en fronteras de oración;
* apunta a 200 palabras y no supera 250 palabras salvo una oración individual
  que ya sea más larga que el límite;
* no usa modelos generativos ni modifica el contenido semántico.

Ejemplo:
    python Fase_2_Chunking/chunk_pdfs.py
    python Fase_2_Chunking/chunk_pdfs.py --objetivo 230 --salida Fase_2_Chunking/salida_pdf
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path



def find_project_root() -> Path:
    """Encuentra la raíz aunque el script esté en Fase_2_Chunking/chunking-pdfs."""
    script_dir = Path(__file__).resolve().parent
    for candidate in (script_dir, *script_dir.parents):
        if (candidate / "Fase_1_Limpieza").is_dir():
            return candidate
    # Mantiene un valor útil para que el error posterior sea explícito.
    return script_dir.parents[1]


PROJECT_ROOT = find_project_root()
_INPUT_CANDIDATES = (
    PROJECT_ROOT / "Fase_1_Limpieza" / "output_final_limpio",
    PROJECT_ROOT / "Fase_1_Limpieza" / "output final limpio",
)
DEFAULT_INPUT = next((path for path in _INPUT_CANDIDATES if path.is_dir()), _INPUT_CANDIDATES[0])
DEFAULT_OUTPUT = PROJECT_ROOT / "Fase_2_Chunking" / "chunking-pdfs"
DEFAULT_TARGET = 200
MAX_WORDS = 250
MIN_CHUNK_WORDS = 15

WORD_RE = re.compile(r"[\w]+(?:[-'][\w]+)*", re.UNICODE)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]+)\]\([^)]*\)")
EXTRACTION_MARKER_RE = re.compile(r"^\s*(?:!+\s*\d+|!{2,}|[~`^]+)\s*$")
PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:\*\*|__|\*|_)?(?:\d{1,4}|[ivxlcdm]{1,12})(?:\*\*|__|\*|_)?\s*$",
    re.IGNORECASE,
)
PDF_PAGE_MARKER_RE = re.compile(
    r"^\s*\*?\s*<!--\s*(?:p[áa]gina|page)\s+\d+\s*-->\s*\*?\s*$",
    re.IGNORECASE,
)
TOC_ENTRY_RE = re.compile(
    r"^(?:[-*+•]\s+)?(?:\d+(?:\.\d+)*[.)]?\s+)?"
    r".+?(?:\.{2,}|\s)\s*\d{1,4}\s*$"
)
TOC_NUMBERED_ENTRY_RE = re.compile(
    r"^\s*\d+(?:\.\d+)*[.)]?\s+.{2,100}(?:\s+\d{1,4})?\s*$"
)
TOC_HEADING_NAMES = {
    "table of contents", "contents", "content", "index of contents",
    "tabla de contenido", "tabla de contenidos", "indice de contenidos",
    "índice de contenidos", "índice", "indice", "sommaire", "sumário",
    "sumario", "目次",
}
END_MATTER_HEADING_NAMES = {
    "references", "reference", "bibliography", "bibliographies",
    "referencias", "referencia", "bibliografía", "bibliografías",
    "works cited", "literatura citada", "fuentes consultadas",
    "acknowledgements", "acknowledgments", "agradecimientos",
    "how to cite", "cómo citar", "como citar", "citation", "citations",
    "credits", "créditos", "creditos", "about the authors",
    "author biographies", "biografías de los autores", "glossary", "glosario",
    "index", "índice analítico", "indice analitico",
}
TOC_CONTENT_TERMS = (
    "table of contents", "contents", "indice", "índice", "introduction",
    "acknowledgements", "acknowledgments", "appendix", "methodology",
    "references", "chapter", "annex", "tabla de contenido", "agradecimientos",
    "apéndice", "metodología", "referencias", "capítulo",
)

TOC_HEADING_EXTRA_NAMES = {
    "sumário", "tabela de conteúdos", "tabela de conteudos",
    "table des matières", "table des matieres", "index des matières",
    "index des matieres",
}
END_MATTER_EXTRA_NAMES = {
    "referências", "bibliografia", "obras citadas", "fontes consultadas",
    "références", "bibliographie", "ouvrages cités", "ouvrages cites",
    "sources consultées", "sources consultees", "agradecimentos",
    "remerciements", "comment citer", "sobre os autores", "a propos des auteurs",
    "à propos des auteurs", "biografias dos autores", "glossário", "glossario",
    "glossaire",
}
TOC_CONTENT_TERMS_EXTRA = (
    "referências", "bibliografia", "tabela de conteúdos", "sumário",
    "références", "bibliographie", "table des matières", "sommaire",
)

ABBREVIATIONS = {
    "sr.", "sra.", "dr.", "dra.", "prof.", "pág.", "págs.", "no.",
    "núm.", "etc.", "e.g.", "i.e.", "vs.", "fig.", "figs.", "inc.",
    "mr.", "mrs.", "ms.", "st.", "jan.", "feb.", "mar.", "apr.",
    "jun.", "jul.", "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
}


def read_text(path: Path) -> str:
    """Lee UTF-8 y tolera residuos de codificación heredados."""
    return path.read_text(encoding="utf-8", errors="replace")


def remove_pdf_artifacts(text: str) -> str:
    """Quita marcadores de página y encabezados/pies claramente repetidos."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    counts: dict[str, int] = {}
    for line in lines:
        value = re.sub(r"[ \t]+", " ", line).strip()
        if value:
            key = value.casefold()
            counts[key] = counts.get(key, 0) + 1

    def repeated_page_line(line: str) -> bool:
        value = re.sub(r"[ \t]+", " ", line).strip()
        if not value or counts.get(value.casefold(), 0) < 3 or len(value) > 140:
            return False
        if URL_RE.search(value) or re.fullmatch(r"(?:p[áa]gina|page)?\s*\d{1,4}", value, re.IGNORECASE):
            return True
        letters = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", "", value)
        return bool(letters) and letters.upper() == letters and len(letters) >= 5

    return "\n".join(
        line for line in lines
        if not PDF_PAGE_MARKER_RE.fullmatch(line)
        and not EXTRACTION_MARKER_RE.fullmatch(line)
        and not PAGE_NUMBER_RE.fullmatch(line)
        and not repeated_page_line(line)
    )


def normalise_text(text: str) -> str:
    """Quita solo ruido de formato, conservando cifras y contenido textual."""
    text = remove_pdf_artifacts(text).replace("\ufeff", "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    # Une palabras cortadas por salto de línea en la extracción de PDF.
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = MARKDOWN_LINK_RE.sub(r"\1", text)
    text = HTML_TAG_RE.sub("", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text)
    text = re.sub(r"^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def is_toc_heading(text: str) -> bool:
    value = re.sub(r"\s+", " ", normalise_text(text)).casefold().strip(" .:-")
    if value in TOC_HEADING_NAMES | TOC_HEADING_EXTRA_NAMES:
        return True
    return bool(re.match(
        r"^(?:table\s+of\s+content|tabla\s+de\s+conten|indice\s+de\s+conten|"
        r"índice\s+de\s+conten|table\s+content|contents\s+and\s+)",
        value,
    )) and word_count(value) <= 10


def is_end_matter_heading(text: str) -> bool:
    value = re.sub(r"\s+", " ", normalise_text(text)).casefold().strip(" .:-")
    if value in END_MATTER_HEADING_NAMES | END_MATTER_EXTRA_NAMES:
        return True
    return value in {
        "how to cite this report", "cómo citar este informe", "como citar este relatório",
        "como citar este relatorio", "comment citer ce rapport",
        "references and further reading", "referencias y lecturas adicionales",
        "referências e leituras adicionais", "références et lectures complémentaires",
        "references / bibliography", "referencias / bibliografía",
        "referências / bibliografia", "références / bibliographie",
    }


def is_toc_entry(line: str, toc_mode: bool) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if TOC_ENTRY_RE.match(stripped):
        return True
    if toc_mode and TOC_NUMBERED_ENTRY_RE.match(stripped):
        return True
    if toc_mode and word_count(stripped) <= 14 and not re.search(r"[.!?。！？]$", stripped):
        return True
    # En muchos PDFs el índice conserva cada entrada como encabezado Markdown
    # sin puntos guía. Mientras estamos dentro del bloque TOC, esos encabezados
    # cortos se consideran navegación y no contenido semántico.
    return toc_mode and bool(HEADING_RE.match(stripped)) and word_count(stripped) <= 20


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text))


def is_numeric_noise(text: str) -> bool:
    """Detecta bloques numéricos sin contexto semántico recuperable."""
    value = text.strip()
    if not value or re.search(r"[A-Za-zÀ-ÿ]", value):
        return False
    if not re.search(r"\d", value):
        return False
    # Porcentajes, monedas y años/fechas conservan significado propio.
    if re.search(r"[%$€£¥₹]|\b(?:19|20)\d{2}\b", value):
        return False
    return True


def is_toc_content_noise(text: str, section: str | None = None) -> bool:
    """Detecta índices aplanados aunque el extractor no conserve el encabezado."""
    if section and is_toc_heading(section):
        return True
    value = text.casefold()
    page_numbers = re.findall(r"(?<!\w)\d{1,3}(?!\w)", value)
    term_count = sum(term in value for term in TOC_CONTENT_TERMS + TOC_CONTENT_TERMS_EXTRA)
    # El formato de tabla por sí solo no es ruido: puede contener datos
    # relevantes. Se exige además vocabulario típico de índice y páginas.
    table_shape = (
        ("|---" in value or value.count("|") >= 6)
        and len(page_numbers) >= 3
        and term_count >= 2
    )
    return table_shape or (len(page_numbers) >= 4 and term_count >= 2)


def estimated_tokens(text: str) -> int:
    """Estimación reproducible; el tokenizer definitivo pertenece a Encoder."""
    return math.ceil(word_count(text) * 1.3)


def sentence_parts(text: str) -> list[str]:
    """Segmenta de forma conservadora, preservando la puntuación."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    parts: list[str] = []
    start = 0
    i = 0
    while i < len(text):
        char = text[i]
        if char not in ".!?。！？":
            i += 1
            continue

        end = i + 1
        while end < len(text) and text[end] in ".!?。！？…\"'”’»)]}":
            end += 1
        next_char = text[end] if end < len(text) else ""
        previous = text[max(start, i - 12):i + 1].lower().strip()
        previous_word = re.findall(r"[\w.]+$", previous)
        abbreviation = bool(previous_word and previous_word[0] in ABBREVIATIONS)
        decimal = i > 0 and i + 1 < len(text) and text[i - 1].isdigit() and text[i + 1].isdigit()
        boundary = end == len(text) or next_char.isspace()

        if boundary and not abbreviation and not decimal:
            part = text[start:end].strip()
            if part:
                parts.append(part)
            start = end
        i = end

    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts or [text]


def blocks_from_markdown(text: str) -> list[tuple[str, str | None]]:
    """Devuelve una unidad grande por sección, no un bloque por párrafo."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raw_blocks: list[tuple[str, str | None]] = []
    pending: list[str] = []
    section: str | None = None
    toc_mode = False
    discard_end_matter = False

    def flush() -> None:
        nonlocal pending
        # Conserva los saltos de fila de tablas para poder dividirlas por
        # filas después. En texto narrativo los saltos se normalizan más
        # adelante al segmentar oraciones.
        value = normalise_text("\n".join(pending))
        if value:
            raw_blocks.append((value, section))
        pending = []

    for line in lines:
        match = HEADING_RE.match(line)
        if match:
            if discard_end_matter:
                # La sección editorial terminó; el siguiente encabezado vuelve
                # a ser contenido normal.
                discard_end_matter = False
            flush()
            heading = normalise_text(match.group(1))
            if is_toc_heading(heading):
                toc_mode = True
                section = None
                continue
            if is_end_matter_heading(heading):
                discard_end_matter = True
                toc_mode = False
                section = None
                continue
            if toc_mode and (TOC_ENTRY_RE.match(heading) or TOC_NUMBERED_ENTRY_RE.match(heading)):
                continue
            toc_mode = False
            if heading:
                section = heading
            continue
        # Algunos extractores pierden el prefijo Markdown del encabezado del
        # índice. Reconocerlo como señal estructural evita que sus entradas se
        # acumulen en el bloque anterior.
        if not toc_mode and is_toc_heading(line):
            flush()
            toc_mode = True
            section = None
            continue
        if not toc_mode and is_end_matter_heading(line):
            flush()
            discard_end_matter = True
            section = None
            continue
        if discard_end_matter:
            continue
        if toc_mode:
            if is_toc_entry(line, toc_mode):
                continue
            # El TOC puede venir aplanado en una línea larga sin puntos guía.
            # Se descarta todo hasta el siguiente encabezado Markdown; ese
            # encabezado es el límite confiable del índice.
            continue
        if not line.strip():
            flush()
            continue
        pending.append(line.strip())
    flush()
    # Los saltos de párrafo siguen siendo útiles para lectura, pero no deben
    # forzar chunks pequeños. Se agrupan los párrafos consecutivos de la misma
    # sección y luego se cortan únicamente por oraciones y tamaño.
    return raw_blocks


CONTINUATION_CONNECTORS = (
    "además", "asimismo", "también", "de igual manera", "del mismo modo",
    "por otra parte", "por otro lado", "igualmente", "en este sentido",
    "en consecuencia", "por consiguiente", "therefore", "furthermore",
    "moreover", "also", "in addition", "likewise", "similarly",
    "além disso", "ademais", "da mesma forma", "igualmente",
)
CHANGE_CONNECTORS = (
    "sin embargo", "no obstante", "en cambio", "por el contrario",
    "finalmente", "en conclusión", "conclusión", "however", "nevertheless",
    "in contrast", "on the other hand", "finally", "in conclusion",
    "contudo", "porém", "em contraste", "finalmente",
)
ANAPHORIC_STARTS = (
    "este ", "esta ", "estos ", "estas ", "dicho ", "dicha ",
    "tales ", "ello ", "ellos ", "ellas ", "the same ", "this ",
    "these ", "such ", "it ", "they ", "isso ", "este ", "essa ",
)
CONTINUITY_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
    "y", "o", "en", "por", "para", "con", "que", "se", "su", "sus",
    "a", "al", "como", "más", "muy", "es", "son", "this", "that", "the",
    "and", "or", "of", "to", "in", "for", "with", "as", "is", "are",
}


def paragraph_continues(previous: str, current: str) -> bool:
    """Señal heurística conservadora de continuidad entre dos párrafos."""
    start = re.sub(r"^[\s\d.)-]+", "", current.casefold()).strip()
    if any(start.startswith(connector) for connector in CHANGE_CONNECTORS):
        return False
    if any(start.startswith(connector) for connector in CONTINUATION_CONNECTORS):
        return True
    if any(start.startswith(prefix) for prefix in ANAPHORIC_STARTS):
        return True

    previous_words = set(re.findall(r"[\wÀ-ÿ]{4,}", previous.casefold()))
    current_words = set(re.findall(r"[\wÀ-ÿ]{4,}", current.casefold()))
    shared = (previous_words & current_words) - CONTINUITY_STOPWORDS
    return len(shared) >= 2 or any(len(word) >= 9 for word in shared)


def group_continuous_paragraphs(
    blocks: list[tuple[str, str | None]], max_words: int
) -> list[tuple[str, str | None]]:
    """Une solo párrafos completos con continuidad y dentro del máximo."""
    grouped: list[tuple[str, str | None]] = []
    for value, section in blocks:
        if not grouped:
            grouped.append((value, section))
            continue
        previous, previous_section = grouped[-1]
        can_join = (
            section == previous_section
            and word_count(previous) + word_count(value) <= max_words
            and (
                paragraph_continues(previous, value)
                or word_count(previous) <= MIN_CHUNK_WORDS
                or word_count(value) <= MIN_CHUNK_WORDS
            )
        )
        if can_join:
            grouped[-1] = (f"{previous}\n\n{value}", section)
        else:
            grouped.append((value, section))
    return grouped


def dedupe_key(text: str) -> str:
    value = normalise_text(text).casefold()
    value = re.sub(r"[*_`~]+", "", value)
    return re.sub(r"[^\w\s]", "", value, flags=re.UNICODE)


def deduplicate_adjacent_blocks(
    blocks: list[tuple[str, str | None]],
) -> tuple[list[tuple[str, str | None]], int]:
    """Elimina repeticiones consecutivas producidas por formato/callouts PDF."""
    result: list[tuple[str, str | None]] = []
    removed = 0
    for value, section in blocks:
        if not result or result[-1][1] != section:
            result.append((value, section))
            continue
        previous, previous_section = result[-1]
        current_key = dedupe_key(value)
        previous_key = dedupe_key(previous)
        if not current_key or not previous_key:
            result.append((value, section))
            continue
        if current_key == previous_key:
            removed += 1
            continue
        current_is_formatted = bool(re.search(r"[*_`]", value))
        current_words = word_count(value)
        if current_words >= 8 and current_key in previous_key:
            if current_is_formatted or len(current_key) / len(previous_key) >= 0.35:
                removed += 1
                continue
        if word_count(previous) >= 8 and previous_key in current_key:
            previous_is_formatted = bool(re.search(r"[*_`]", previous))
            if previous_is_formatted or len(previous_key) / len(current_key) >= 0.35:
                result[-1] = (value, section)
                removed += 1
                continue
        result.append((value, section))
    return result, removed


TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$"
)


def is_table_block(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return len(lines) >= 2 and (
        any(TABLE_SEPARATOR_RE.fullmatch(line) for line in lines)
        or sum(line.startswith("|") for line in lines) >= 2
    )


def structured_rows(text: str) -> list[str]:
    """Conserva filas de tablas, excluyendo solo la fila separadora Markdown."""
    rows = []
    for line in text.splitlines():
        value = line.strip()
        if not value or TABLE_SEPARATOR_RE.fullmatch(value):
            continue
        rows.append(value)
    return rows


def hard_split_words(text: str, max_words: int) -> list[str]:
    words = text.split()
    return [" ".join(words[index:index + max_words]) for index in range(0, len(words), max_words)]


def split_long_unit(text: str, max_words: int) -> list[tuple[str, str]]:
    """Divide una unidad que no cabe, priorizando suboraciones y luego palabras."""
    clauses = [part.strip() for part in re.split(r"(?<=[,;:])\s+|\s+[—–-]\s+", text) if part.strip()]
    if len(clauses) <= 1:
        return [(part, "limite_palabras") for part in hard_split_words(text, max_words)]
    result: list[tuple[str, str]] = []
    current: list[str] = []
    current_words = 0
    for clause in clauses:
        count = word_count(clause)
        if count > max_words:
            if current:
                result.append((" ".join(current), "suboracion"))
                current, current_words = [], 0
            result.extend((part, "limite_palabras") for part in hard_split_words(clause, max_words))
            continue
        if current and current_words + count > max_words:
            result.append((" ".join(current), "suboracion"))
            current, current_words = [], 0
        current.append(clause)
        current_words += count
    if current:
        result.append((" ".join(current), "suboracion"))
    return result


def chunks_for_structured_block(
    text: str,
    section: str | None,
    target: int,
    max_words: int,
    annotate_split: bool = False,
) -> tuple[list[dict], list[str]]:
    """Agrupa tablas por filas y evita convertirlas en una falsa oración."""
    rows = structured_rows(text)
    chunks: list[dict] = []
    warnings: list[str] = []
    current: list[str] = []
    current_words = 0
    limit = min(target, max_words)

    def close() -> None:
        nonlocal current, current_words
        if current:
            item = {
                "texto": "\n".join(current).strip(),
                "seccion": section,
                "advertencias": [],
            }
            if annotate_split:
                item["separado_por"] = "fila_tabla"
            chunks.append(item)
            current = []
            current_words = 0

    for row in rows:
        count = word_count(row)
        if count > max_words:
            # Una fila de tabla no tiene fronteras oracionales confiables;
            # dividirla por celdas es menos dañino que emitir un chunk enorme.
            cells = [cell.strip() for cell in row.strip("|").split("|") if cell.strip()]
            cell_group: list[str] = []
            cell_words = 0
            for cell in cells:
                cell_count = word_count(cell)
                if annotate_split and cell_count > max_words:
                    if cell_group:
                        item = {
                            "texto": " | ".join(cell_group),
                            "seccion": section,
                            "advertencias": ["fila de tabla dividida por celdas"],
                            "separado_por": "celda_tabla",
                        }
                        chunks.append(item)
                        cell_group, cell_words = [], 0
                    for part in hard_split_words(cell, max_words):
                        chunks.append({
                            "texto": part,
                            "seccion": section,
                            "advertencias": ["celda de tabla dividida por límite de palabras"],
                            "separado_por": "limite_palabras",
                        })
                    continue
                if cell_group and cell_words + cell_count > max_words:
                    item = {
                        "texto": " | ".join(cell_group),
                        "seccion": section,
                        "advertencias": ["fila de tabla dividida por celdas"],
                    }
                    if annotate_split:
                        item["separado_por"] = "celda_tabla"
                    chunks.append(item)
                    cell_group, cell_words = [], 0
                cell_group.append(cell)
                cell_words += cell_count
            if cell_group:
                item = {
                    "texto": " | ".join(cell_group),
                    "seccion": section,
                    "advertencias": ["fila de tabla dividida por celdas"],
                }
                if annotate_split:
                    item["separado_por"] = "celda_tabla"
                chunks.append(item)
            warnings.append(f"fila estructurada de {count} palabras dividida por celdas")
            continue
        if current and current_words + count > limit:
            close()
        current.append(row)
        current_words += count
    close()
    return chunks, warnings


def chunks_for_block(
    text: str,
    section: str | None,
    target: int,
    max_words: int,
    overlap_sentences: int = 0,
    annotate_split: bool = False,
) -> tuple[list[dict], list[str]]:
    if is_table_block(text):
        return chunks_for_structured_block(text, section, target, max_words, annotate_split)
    sentences = sentence_parts(text)
    chunks: list[dict] = []
    warnings: list[str] = []
    index = 0
    while index < len(sentences):
        start_index = index
        current: list[str] = []
        current_words = 0
        while index < len(sentences):
            sentence = sentences[index]
            count = word_count(sentence)
            if count > max_words:
                if not current:
                    if annotate_split:
                        for piece, split_kind in split_long_unit(sentence, max_words):
                            chunks.append({
                                "texto": piece,
                                "seccion": section,
                                "advertencias": ["unidad larga dividida para respetar el máximo de 250 palabras"],
                                "separado_por": split_kind,
                            })
                        index += 1
                        warnings.append(
                            f"oración de {count} palabras dividida para respetar el máximo"
                        )
                        continue
                    current.append(sentence)
                    current_words = count
                    index += 1
                    warnings.append(
                        f"oración de {count} palabras; no se dividió para conservar completitud"
                    )
                break
            if current and current_words + count > min(target, max_words):
                break
            current.append(sentence)
            current_words += count
            index += 1

        if not current:
            if index >= len(sentences):
                # La última oración larga ya fue dividida y agregada arriba.
                break
            # Salvaguarda para no bloquear el proceso ante un caso inesperado.
            current = [sentences[index]]
            current_words = word_count(sentences[index])
            index += 1
        value = " ".join(current).strip()
        chunks.append({
            "texto": value,
            "seccion": section,
            **({
                "separado_por": (
                    "oracion_larga_conservada"
                    if any(word_count(sentence) > max_words for sentence in current)
                    else "oracion"
                )
            } if annotate_split else {}),
        })

        if overlap_sentences and index < len(sentences):
            next_sentence = sentences[index]
            related = paragraph_continues(" ".join(current), next_sentence)
            if related:
                index = max(
                    start_index + 1,
                    index - min(overlap_sentences, len(current)),
                )
    return chunks, warnings


def semantic_chunks_for_section(
    text: str,
    section: str | None,
    target: int,
    max_words: int,
    model: object,
    threshold: float,
) -> tuple[list[dict], list[str]]:
    """Fragmenta por cambios de similitud entre oraciones consecutivas."""
    sentences = sentence_parts(text)
    if len(sentences) <= 1:
        return ([{"texto": text.strip(), "seccion": section, "advertencias": []}] if text.strip() else []), []

    try:
        import numpy as np
        embeddings = model.encode(
            sentences,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except ImportError as exc:
        raise RuntimeError(
            "El modo semantic requiere sentence-transformers y numpy."
        ) from exc

    similarities = np.sum(embeddings[:-1] * embeddings[1:], axis=1)
    chunks: list[dict] = []
    warnings: list[str] = []
    current: list[str] = []
    current_words = 0

    def close() -> None:
        nonlocal current, current_words
        if current:
            chunks.append({
                "texto": " ".join(current).strip(),
                "seccion": section,
                "advertencias": [],
            })
            current = []
            current_words = 0

    for index, sentence in enumerate(sentences):
        count = word_count(sentence)
        if current and current_words + count > max_words:
            close()
        current.append(sentence)
        current_words += count

        has_boundary = index < len(similarities) and (1.0 - float(similarities[index])) >= threshold
        next_count = word_count(sentences[index + 1]) if index + 1 < len(sentences) else 0
        reaches_target = current_words >= target
        next_would_exceed = current_words + next_count > max_words
        if (has_boundary and reaches_target) or next_would_exceed or index == len(sentences) - 1:
            close()

    close()
    return chunks, warnings


def load_manifest(input_root: Path, manifest_path: Path | None) -> list[dict]:
    path = manifest_path or input_root / "manifiesto_final_limpio.json"
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el manifiesto de Fase 1: {path}")
    data = json.loads(read_text(path))
    records = []
    for item in data:
        if str(item.get("formato", "")).lower() != "pdf":
            continue
        relative = item.get("ruta_final")
        candidate = input_root / Path(str(relative)) if relative else None
        if candidate and candidate.exists():
            item = dict(item)
            item["_path"] = candidate
            records.append(item)
    return records


def fallback_records(input_root: Path) -> list[dict]:
    """Fallback explícito para una carpeta oficial sin manifiesto."""
    records = []
    for path in sorted(input_root.rglob("*.md")) + sorted(input_root.rglob("*.txt")):
        if not re.search(r"(?:^|[\\/])pdfs?(?:_full)?(?:[\\/]|$)", str(path), re.I):
            continue
        match = re.search(r"DOC-\d+", path.stem, re.I)
        if not match:
            continue
        phenomenon = re.search(r"F([123])_", str(path), re.I)
        records.append({
            "doc_id": match.group(0).upper(),
            "fuente": path.stem,
            "ruta_original": path.stem + ".pdf",
            "fenomeno": int(phenomenon.group(1)) if phenomenon else None,
            "idioma": "unknown",
            "_path": path,
        })
    return records


def process_record(
    record: dict,
    target: int,
    max_words: int,
    overlap_sentences: int,
    mode: str,
    semantic_model: object | None = None,
    semantic_threshold: float = 0.80,
) -> tuple[list[dict], list[str], int]:
    text = normalise_text(read_text(record["_path"]))
    blocks, deduped_count = deduplicate_adjacent_blocks(blocks_from_markdown(text))
    blocks = group_continuous_paragraphs(blocks, max_words)
    output: list[dict] = []
    warnings: list[str] = []
    if mode == "semantic":
        if semantic_model is None:
            raise RuntimeError("No se cargó el encoder para el modo semantic.")
        for block, section in blocks:
            made, section_warnings = semantic_chunks_for_section(
                block,
                section,
                target,
                max_words,
                semantic_model,
                semantic_threshold,
            )
            output.extend(made)
            warnings.extend(section_warnings)
    elif overlap_sentences == 0:
        for block, section in blocks:
            block_words = word_count(block)
            if block_words > max_words:
                made, block_warnings = chunks_for_block(
                    block, section, target, max_words, overlap_sentences,
                    annotate_split=(mode == "standard"),
                )
                output.extend(made)
                warnings.extend(block_warnings)
                continue
            else:
                output.append({
                    "texto": block,
                    "seccion": section,
                    "advertencias": [],
                })
    else:
        # Las variantes con solapamiento conservan el comportamiento
        # experimental basado en oraciones.
        for block, section in blocks:
            made, block_warnings = chunks_for_block(
                block, section, target, max_words, overlap_sentences,
                annotate_split=(mode == "standard"),
            )
            output.extend(made)
            warnings.extend(block_warnings)
    if mode == "late_chunking":
        cursor = 0
        for part in output:
            span = find_normalized_span(text, part["texto"], cursor)
            if span is None:
                start, end = cursor, cursor + len(part["texto"])
            else:
                start, end = span
            part["char_start"] = start
            part["char_end"] = end
            cursor = end
    return output, warnings, deduped_count


def find_normalized_span(source: str, candidate: str, cursor: int) -> tuple[int, int] | None:
    """Encuentra un chunk permitiendo diferencias entre espacios y saltos."""
    tokens = re.findall(r"\S+", candidate)
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, source[cursor:], flags=re.DOTALL)
    if not match:
        return None
    return cursor + match.start(), cursor + match.end()


def build_chunk(record: dict, part: dict, position: int, mode: str) -> dict:
    text = part["texto"]
    chunk = {
        "doc_id": record["doc_id"],
        "chunk_id": f"{record['doc_id']}-CH-{position:04d}",
        "fuente": f"{record.get('fuente') or Path(record['ruta_original']).stem}.pdf",
        "ruta_original": record.get("ruta_original"),
        "formato": "pdf",
        "fenomeno": record.get("fenomeno"),
        "posicion": position,
        "seccion": part.get("seccion"),
        "idioma": record.get("idioma", "unknown"),
        "num_palabras": word_count(text),
        "num_tokens": estimated_tokens(text),
        "chunking_mode": mode,
        "texto": text,
    }
    if mode == "late_chunking":
        chunk.update({
            "char_start": part.get("char_start", 0),
            "char_end": part.get("char_end", len(text)),
            "offsets_base": "texto_normalizado_del_documento",
        })
    if part.get("separado_por"):
        chunk["separado_por"] = part["separado_por"]
    return chunk


def run(args: argparse.Namespace) -> int:
    input_root = Path(args.entrada)
    output_root = Path(args.salida)
    if not args.sin_subcarpeta:
        label = f"_{args.etiqueta}" if args.etiqueta else ""
        output_root = output_root / (
            f"pdfs_{args.modo}_objetivo-{args.objetivo}palabras_"
            f"max-{args.maximo}_solapamiento-{args.solapamiento}{label}"
        )
    try:
        try:
            records = load_manifest(input_root, Path(args.manifiesto) if args.manifiesto else None)
        except FileNotFoundError:
            if not args.permitir_sin_manifest:
                raise
            records = fallback_records(input_root)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error leyendo la entrada: {exc}", file=sys.stderr)
        return 1

    semantic_model = None
    if args.modo == "semantic":
        try:
            from sentence_transformers import SentenceTransformer
            semantic_model = SentenceTransformer(args.encoder)
        except ImportError as exc:
            print(
                "El modo semantic requiere instalar sentence-transformers y numpy.",
                file=sys.stderr,
            )
            return 1
        except Exception as exc:
            print(f"No se pudo cargar el encoder semántico: {exc}", file=sys.stderr)
            return 1

    output_root.mkdir(parents=True, exist_ok=True)
    metadata_jsonl_path = output_root / "metadata.jsonl"
    metadata_json_path = output_root / "metadata.json"
    report_path = output_root / "reporte_chunking_pdf.json"
    report = {
        "configuracion": {
            "estrategia": "estructural_oracional",
            "objetivo_palabras": args.objetivo,
            "minimo_palabras": MIN_CHUNK_WORDS,
            "maximo_palabras": args.maximo,
            "solapamiento_oraciones": args.solapamiento,
            "modo": args.modo,
            "encoder_semantico": args.encoder if args.modo == "semantic" else None,
            "umbral_distancia_semantica": args.umbral_semantic if args.modo == "semantic" else None,
            "agrupacion": "parrafos consecutivos con señal de continuidad tematica, misma seccion y limite de palabras",
            "filtrado_toc": True,
            "token_count": "estimacion_determinista; reemplazar por tokenizer del encoder en Fase 3",
            "entrada": str(input_root),
        },
        "resumen": {"documentos_en_manifest": len(records), "documentos_procesados": 0,
                    "documentos_vacios": 0, "documentos_con_error": 0,
            "chunks_generados": 0,
            "chunks_omitidos_total": 0,
            "chunks_omitidos_por_minimo": 0,
            "chunks_omitidos_numericos": 0,
            "chunks_omitidos_toc": 0,
            "chunks_con_alertas": 0,
            "advertencias_proceso": 0,
            "separaciones_forzadas": {},
            "bloques_duplicados_omitidos": 0},
        "alertas_por_documento": {},
        "errores": [],
        "documentos": [],
        "documentos_vacios": [],
    }

    all_chunks: list[dict] = []
    with metadata_jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            try:
                raw_parts, warnings, deduped_count = process_record(
                    record, args.objetivo, args.maximo, args.solapamiento, args.modo,
                    semantic_model, args.umbral_semantic
                )
                report["resumen"]["bloques_duplicados_omitidos"] += deduped_count
                parts = []
                omitted_counts = {"minimo": 0, "numerico": 0, "toc": 0}
                for part in raw_parts:
                    if word_count(part["texto"]) <= MIN_CHUNK_WORDS:
                        omitted_counts["minimo"] += 1
                    elif is_numeric_noise(part["texto"]):
                        omitted_counts["numerico"] += 1
                    elif is_toc_content_noise(part["texto"], part.get("seccion")):
                        omitted_counts["toc"] += 1
                    else:
                        parts.append(part)
                omitted = sum(omitted_counts.values())
                report["resumen"]["chunks_omitidos_total"] += omitted
                report["resumen"]["chunks_omitidos_por_minimo"] += omitted_counts["minimo"]
                report["resumen"]["chunks_omitidos_numericos"] += omitted_counts["numerico"]
                report["resumen"]["chunks_omitidos_toc"] += omitted_counts["toc"]
                if not parts:
                    report["resumen"]["documentos_vacios"] += 1
                    empty_detail = {
                        "doc_id": record.get("doc_id"),
                        "fuente": record.get("fuente"),
                        "ruta_original": record.get("ruta_original"),
                        "archivo_procesado": str(record.get("_path")),
                        "motivo": "sin texto o sin chunks después de aplicar los filtros",
                    }
                    report["documentos_vacios"].append(empty_detail)
                    report["alertas_por_documento"][record["doc_id"]] = [{
                        "chunk_id": None,
                        "mensaje": "documento sin chunks validos despues del filtro minimo",
                        "tipo": "documento_vacio",
                    }]
                    report["documentos"].append({
                        "doc_id": record["doc_id"],
                        "chunks": 0,
                        "chunks_omitidos_total": omitted,
                        "chunks_omitidos_por_minimo": omitted_counts["minimo"],
                        "chunks_omitidos_numericos": omitted_counts["numerico"],
                        "chunks_omitidos_toc": omitted_counts["toc"],
                        "advertencias": ["sin chunks despues de aplicar filtros"],
                    })
                    continue
                doc_alertas = []
                for position, part in enumerate(parts):
                    chunk = build_chunk(record, part, position, args.modo)
                    all_chunks.append(chunk)
                    handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
                    for message in part.get("advertencias", []):
                        doc_alertas.append({
                            "chunk_id": chunk["chunk_id"],
                            "mensaje": message,
                            "tipo": "advertencia_chunk",
                        })
                    split_kind = part.get("separado_por")
                    if split_kind:
                        doc_alertas.append({
                            "chunk_id": chunk["chunk_id"],
                            "mensaje": f"separado_por={split_kind}",
                            "tipo": "separacion",
                        })
                        report["resumen"]["separaciones_forzadas"][split_kind] = (
                            report["resumen"]["separaciones_forzadas"].get(split_kind, 0) + 1
                        )
                    if word_count(part["texto"]) > args.maximo:
                        doc_alertas.append({
                            "chunk_id": chunk["chunk_id"],
                            "mensaje": f"chunk de {word_count(part['texto'])} palabras; se conservó la oración completa",
                        })
                report["resumen"]["documentos_procesados"] += 1
                report["resumen"]["chunks_generados"] += len(parts)
                if warnings:
                    for warning in warnings:
                        doc_alertas.append({
                            "chunk_id": None,
                            "mensaje": warning,
                            "tipo": "advertencia_proceso",
                        })
                    report["resumen"]["advertencias_proceso"] += len(warnings)
                report["resumen"]["chunks_con_alertas"] += len({
                    item["chunk_id"] for item in doc_alertas if item.get("chunk_id")
                })
                if doc_alertas:
                    report["alertas_por_documento"][record["doc_id"]] = doc_alertas
                report["documentos"].append({
                    "doc_id": record["doc_id"],
                    "chunks": len(parts),
                    "chunks_omitidos_total": omitted,
                    "chunks_omitidos_por_minimo": omitted_counts["minimo"],
                    "chunks_omitidos_numericos": omitted_counts["numerico"],
                    "chunks_omitidos_toc": omitted_counts["toc"],
                    "alertas": doc_alertas,
                })
            except (OSError, UnicodeError, KeyError) as exc:
                report["resumen"]["documentos_con_error"] += 1
                report["errores"].append({"doc_id": record.get("doc_id"), "archivo": str(record.get("_path")), "error": str(exc)})

    metadata_json_path.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Listo: {metadata_jsonl_path}")
    print(f"Listo: {metadata_json_path}")
    print(f"Reporte: {report_path}")
    print(json.dumps(report["resumen"], ensure_ascii=False))
    if report["documentos_vacios"]:
        print("Documentos sin chunks válidos:")
        for empty in report["documentos_vacios"]:
            print(
                f"- {empty['doc_id']} | {empty.get('fuente')} | "
                f"{empty['motivo']}"
            )
    else:
        print("Documentos sin chunks válidos: ninguno")
    return 0 if not report["errores"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", default=str(DEFAULT_INPUT), help="carpeta output final limpio de Fase 1")
    parser.add_argument("--salida", default=str(DEFAULT_OUTPUT), help="carpeta de salida de los chunks")
    parser.add_argument("--manifiesto", default=None, help="ruta alternativa al manifiesto JSON")
    parser.add_argument("--objetivo", type=int, default=DEFAULT_TARGET,
                        help="tamaño objetivo en palabras; por defecto 200")
    parser.add_argument("--maximo", type=int, default=MAX_WORDS)
    parser.add_argument("--solapamiento", type=int, default=0)
    parser.add_argument("--modo", choices=("standard", "late_chunking", "semantic"), default="standard")
    parser.add_argument("--etiqueta", default="")
    parser.add_argument("--encoder", default="BAAI/bge-m3",
                        help="encoder para modo semantic; por defecto BAAI/bge-m3")
    parser.add_argument("--umbral-semantic", type=float, default=0.80,
                        help="distancia 1-coseno para detectar cambio tematico")
    parser.add_argument("--separar-experimento", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--sin-subcarpeta", action="store_true",
                        help="guarda directamente en la carpeta indicada por --salida")
    parser.add_argument("--permitir-sin-manifest", action="store_true",
                        help="permite inferir PDF desde carpetas pdfs si falta el manifiesto")
    args = parser.parse_args()
    if not 1 <= args.objetivo <= args.maximo <= MAX_WORDS:
        parser.error(f"debe cumplirse 1 <= --objetivo <= --maximo <= {MAX_WORDS}")
    if args.solapamiento < 0:
        parser.error("--solapamiento no puede ser negativo")
    if not 0 <= args.umbral_semantic <= 2:
        parser.error("--umbral-semantic debe estar entre 0 y 2")
    if args.modo == "semantic" and args.solapamiento != 0:
        parser.error("el modo semantic requiere --solapamiento 0")
    return args


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
