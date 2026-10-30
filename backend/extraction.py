"""PDF text/OCR extraction and candidate-fact heuristics for document uploads.

Fully offline: pymupdf for the text layer, optional local tesseract for OCR,
and a hand-written keyword/regex parser for candidate facts. No network calls,
no LLM/AI involved — see extract_candidate_facts() for why that's a hard limit.
"""

import io
import re
import shutil
from datetime import datetime

import pymupdf

from schemas import FactType


class InvalidPDFError(Exception):
    """Raised when the uploaded bytes can't be parsed as a PDF at all."""


def extract_pages(file_bytes: bytes) -> list[str]:
    """Return each page's text layer (possibly empty strings). Never writes
    the bytes to disk — pymupdf opens straight from the in-memory stream."""
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:  # pymupdf raises its own exception types on corrupt input
        raise InvalidPDFError(f"Could not parse PDF: {exc}") from exc
    try:
        return [page.get_text() for page in doc]
    except Exception as exc:
        raise InvalidPDFError(f"Could not parse PDF: {exc}") from exc
    finally:
        doc.close()


def ocr_available() -> bool:
    """Whether OCR can actually be attempted right now. Standalone and
    patchable so tests can force either branch regardless of this host."""
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def ocr_pages(file_bytes: bytes) -> list[str]:
    """Render each page to an image and run local tesseract OCR on it. Only
    call this when ocr_available() is True and the text layer was empty."""
    import pytesseract
    from PIL import Image

    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        texts = []
        for page in doc:
            pix = page.get_pixmap()
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            texts.append(pytesseract.image_to_string(image))
        return texts
    finally:
        doc.close()


# --- Candidate fact extraction ---
#
# ponytail: this is a naive keyword/regex heuristic, not NLP/AI — it matches a
# trigger word and reads the rest of that one line. Known ceiling: misses
# facts phrased across multiple lines or without one of the listed keywords.
# Upgrade path: a proper NLP/IE pipeline, if real-world document variety ever
# demands it (explicitly out of scope for this phase: no AI-based extraction).

_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
_DATE_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}|\d{1,2}\s+(?:" + _MONTHS + r")\s+\d{4}",
    re.IGNORECASE,
)

_CUSTODY_START_KEYWORDS = ("custody start", "arrested on", "detained on", "taken into custody")
_CUSTODY_END_KEYWORDS = ("custody end", "released on", "bail granted on")
# ponytail-found bug (Phase 7 review): bare "section"/"ipc" used to be in this
# tuple, but those also match a typical max_punishment_source line ("Section
# 379 IPC provides for: ..."), so current_charges could get misattributed
# that line's text if it appeared before the real charges line. "charge" and
# "accused of" are precise enough on their own not to need them.
_CHARGE_KEYWORDS = ("charge", "accused of")
_MAX_PUNISHMENT_KEYWORDS = ("maximum punishment", "punishable")
_MAX_PUNISHMENT_SOURCE_KEYWORDS = ("provides for", "under section")
_PENDING_CASE_KEYWORDS = ("pending case", "fir no", "other proceeding")
_EXCEPTION_KEYWORDS = ("juvenile", "first-time offender", "medical ground", "senior citizen")
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*year", re.IGNORECASE)
_DEATH_OR_LIFE_KEYWORDS = ("death", "life imprisonment", "imprisonment for life")
# ponytail: a naive negation guard, not real NLP -- catches "not/no/without/
# except death penalty" but not every possible phrasing. Upgrade path: proper
# NLP/IE, explicitly out of scope for this phase (no AI-based extraction).
_NEGATION_WORDS = ("not ", "no ", "without ", "excluding ", "except ")


def _parse_date(line: str) -> str | None:
    match = _DATE_RE.search(line)
    if not match:
        return None
    raw = match.group(0)
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _value_after_colon(line: str) -> str | None:
    if ":" not in line:
        return None
    value = line.split(":", 1)[1].strip()
    return value or None


def _list_after_colon(line: str) -> list[str] | None:
    value = _value_after_colon(line)
    if not value:
        return None
    items = [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
    return items or None


def extract_candidate_facts(pages: list[str]) -> dict[FactType, dict]:
    """Scan page texts for simple keyword/date patterns. Returns only the
    fact types actually found — callers must treat an absent key as unknown,
    never invent a value."""
    found: dict[FactType, dict] = {}

    for page_num, text in enumerate(pages, start=1):
        if not text:
            continue
        for line in text.splitlines():
            lower = line.lower()

            if FactType.custody_start_date not in found and any(k in lower for k in _CUSTODY_START_KEYWORDS):
                date_value = _parse_date(line)
                if date_value:
                    found[FactType.custody_start_date] = {"value": date_value, "page": page_num}

            if FactType.custody_end_date not in found and any(k in lower for k in _CUSTODY_END_KEYWORDS):
                date_value = _parse_date(line)
                if date_value:
                    found[FactType.custody_end_date] = {"value": date_value, "page": page_num}

            if FactType.current_charges not in found and any(k in lower for k in _CHARGE_KEYWORDS):
                charges = _list_after_colon(line)
                if charges:
                    found[FactType.current_charges] = {"value": charges, "page": page_num}

            if FactType.max_punishment not in found and any(k in lower for k in _MAX_PUNISHMENT_KEYWORDS):
                value = _value_after_colon(line)
                if value:
                    found[FactType.max_punishment] = {"value": value, "page": page_num}
                years_match = _YEARS_RE.search(line)
                if years_match and FactType.max_punishment_years not in found:
                    found[FactType.max_punishment_years] = {"value": float(years_match.group(1)), "page": page_num}

            # Never set False here — absence of the keyword doesn't prove the offence
            # excludes death/life imprisonment, only a reviewer can confirm that negative.
            # Also skip an obviously negated sentence ("not death penalty") rather than
            # assert True from it -- a wrong True candidate here is worse than none,
            # since it pushes the rule engine toward ESCALATED_LEGAL_REVIEW if trusted.
            if (
                FactType.death_or_life_punishment not in found
                and any(k in lower for k in _DEATH_OR_LIFE_KEYWORDS)
                and not any(neg in lower for neg in _NEGATION_WORDS)
            ):
                found[FactType.death_or_life_punishment] = {"value": True, "page": page_num}

            if FactType.max_punishment_source not in found and any(
                k in lower for k in _MAX_PUNISHMENT_SOURCE_KEYWORDS
            ):
                value = _value_after_colon(line)
                if value:
                    found[FactType.max_punishment_source] = {"value": value, "page": page_num}

            if FactType.other_pending_cases not in found and any(k in lower for k in _PENDING_CASE_KEYWORDS):
                cases = _list_after_colon(line)
                if cases:
                    found[FactType.other_pending_cases] = {"value": cases, "page": page_num}

            if FactType.exception_flags not in found:
                hits = [kw for kw in _EXCEPTION_KEYWORDS if kw in lower]
                if hits:
                    found[FactType.exception_flags] = {"value": hits, "page": page_num}

    return found
