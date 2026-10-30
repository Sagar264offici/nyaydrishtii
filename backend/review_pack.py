"""Counsel Review Pack PDF generator.

Renders a case's CURRENT recorded state (case record, facts, evaluation
history) into a PDF for human counsel review. This module never computes or
infers anything new -- no Section 479 evaluation is ever run here, no
custody date or fact value is ever invented. It only formats what is already
persisted. See GET /api/cases/{case_id}/review-pack in main.py.

ponytail: one flat module with plain helper functions, not a templating
engine or a class hierarchy -- there is exactly one document layout.
reportlab is the one new dependency this phase needed (stdlib has no PDF
writer, and nothing already installed does tables/pagination/text-wrapping).
"""

from __future__ import annotations

import io
from datetime import date as _date
from datetime import datetime
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from schemas import FactType, VerificationStatus

DISCLAIMER_SHORT = (
    "DRAFT — Counsel Review Aid. Not a judicial determination, bail order, "
    "or release authorization."
)
DISCLAIMER_FULL = (
    "This document is a draft aid prepared to support counsel review. It is a "
    "structured summary of facts and an internal rule-engine review-status flag "
    "already on record for this case. It is NOT a judicial determination, NOT a "
    "bail order, and NOT a release authorization, and it does not itself "
    "establish eligibility for release. All facts and figures below are only "
    "as reliable as their verification status indicates. Generated from "
    "synthetic demonstration data."
)

_FACT_LABELS: dict[str, str] = {
    "custody_start_date": "Custody Start Date",
    "custody_end_date": "Custody End Date",
    "current_charges": "Current Charges",
    "max_punishment": "Maximum Punishment",
    "max_punishment_years": "Maximum Punishment — Years",
    "max_punishment_source": "Maximum Punishment — Source",
    "death_or_life_punishment": "Death or Life Imprisonment Specified?",
    "other_pending_cases": "Other Pending Cases",
    "exception_flags": "Exception Flags",
    "accused_caused_delay_days": "Accused-Caused Delay (days)",
}

_STATUS_LABELS: dict[str, str] = {
    "unknown": "UNKNOWN — not found in any uploaded document",
    "unverified": "UNVERIFIED — extracted, not reviewer-confirmed",
    "verified": "VERIFIED",
    "conflict": "CONFLICT — flagged by a reviewer",
}

_PAGE_W, _PAGE_H = A4
_MARGIN = 0.7 * inch
_CW = _PAGE_W - 2 * _MARGIN  # usable content width


def _cols(*fractions: float) -> list[float]:
    return [_CW * f for f in fractions]


def _esc(value) -> str:
    if value is None:
        return ""
    return _xml_escape(str(value))


def _fact_value_text(value) -> str:
    if value is None:
        return "— not available —"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "(none recorded)"
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _fact_by_type(facts: list[dict]) -> dict[str, dict]:
    return {f["fact_type"]: f for f in facts}


def _wrap_rows(rows: list[list], style) -> list[list]:
    """Row 0 (the header) is left as plain strings, so TableStyle's bold
    header formatting applies. Every other row's string cells become
    Paragraphs, so long text wraps inside its column instead of overflowing."""
    return [
        row if i == 0 else [_p(_esc(c), style) if isinstance(c, str) else c for c in row]
        for i, row in enumerate(rows)
    ]


def _p(text: str, style) -> Paragraph:
    return Paragraph(text, style)


class _ReviewPackCanvas(Canvas):
    """Draws a persistent header (draft designation) and footer (case ID,
    generation timestamp, page X of Y) on every page. The page count isn't
    known until all pages are drawn, so pages are buffered and the footer is
    drawn for all of them in save() -- the standard reportlab recipe for
    'Page X of Y'."""

    def __init__(self, *args, case_id: str, generated_at_label: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._case_id = case_id
        self._generated_at_label = generated_at_label
        self._saved_page_states: list[dict] = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_chrome(total_pages)
            Canvas.showPage(self)
        Canvas.save(self)

    def _draw_chrome(self, total_pages: int) -> None:
        self.setFont("Helvetica-Bold", 8)
        self.setFillColor(colors.HexColor("#92650a"))
        self.drawCentredString(_PAGE_W / 2, _PAGE_H - 0.45 * inch, DISCLAIMER_SHORT)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawString(
            _MARGIN,
            0.45 * inch,
            f"NyayDrishti Counsel Review Pack · {self._case_id} · Generated {self._generated_at_label}",
        )
        self.drawRightString(_PAGE_W - _MARGIN, 0.45 * inch, f"Page {self._pageNumber} of {total_pages}")
        self.setFillColor(colors.black)


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("RPH1", parent=base["Heading1"], fontSize=16, spaceAfter=10),
        "h2": ParagraphStyle("RPH2", parent=base["Heading2"], fontSize=12.5, spaceBefore=16, spaceAfter=6),
        "body": ParagraphStyle("RPBody", parent=base["BodyText"], fontSize=9.5, leading=13),
        "cell": ParagraphStyle("RPCell", parent=base["BodyText"], fontSize=8.5, leading=11),
        "note": ParagraphStyle("RPNote", parent=base["BodyText"], fontSize=9.5, leading=13, textColor=colors.HexColor("#b42318")),
        "small": ParagraphStyle("RPSmall", parent=base["BodyText"], fontSize=8, leading=10.5, textColor=colors.grey),
    }


def _table(rows: list[list], col_fractions: list[float], cell_style) -> Table:
    data = _wrap_rows(rows, cell_style)
    t = Table(data, colWidths=_cols(*col_fractions), repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f2f2")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def generate_review_pack_pdf(
    case: dict,
    facts: list[dict],
    evaluations: list[dict],
    generated_at: datetime,
) -> bytes:
    """Render the review pack. `evaluations` must already be sorted newest
    first (as database.list_evaluations returns it) -- evaluations[0], if
    present, is "the most recent evaluation". This function reads only what
    is passed in; it never queries a database or runs a new rule evaluation."""
    s = _styles()
    story: list = []
    generated_at_label = generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    facts_by_type = _fact_by_type(facts)
    latest_eval = evaluations[0] if evaluations else None

    # --- Title & disclaimer -------------------------------------------------
    story.append(_p("Counsel Review Pack", s["h1"]))
    story.append(_p(f"Case {_esc(case['case_id'])} · Synthetic Demonstration Data", s["body"]))
    story.append(Spacer(1, 6))
    disclaimer_box = Table([[_p(_esc(DISCLAIMER_FULL), s["note"])]], colWidths=_cols(1.0))
    disclaimer_box.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#eab308")),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3cd")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(disclaimer_box)
    story.append(Spacer(1, 10))

    # --- 1. Case overview ----------------------------------------------------
    story.append(_p("1. Case Overview", s["h2"]))
    overview_rows = [
        ["Field", "Value"],
        ["Case ID", case["case_id"]],
        ["Review Status", case["review_status"]],
        ["Assigned Reviewer", case["assigned_reviewer"]],
        ["Report Generated At", generated_at_label],
    ]
    story.append(_table(overview_rows, [0.32, 0.68], s["cell"]))
    story.append(Spacer(1, 8))

    # --- 2. Custody timeline ---------------------------------------------------
    story.append(_p("2. Custody Timeline", s["h2"]))
    start_fact = facts_by_type.get(FactType.custody_start_date.value)
    end_fact = facts_by_type.get(FactType.custody_end_date.value)

    def _date_row(label: str, fact: dict | None) -> list[str]:
        if fact is None:
            return [label, "— no document uploaded for this case yet —", _STATUS_LABELS["unknown"]]
        return [
            label,
            _fact_value_text(fact["value"]),
            _STATUS_LABELS.get(fact["verification_status"], fact["verification_status"]),
        ]

    duration_text = "Cannot compute — custody_start_date is not reviewer-verified."
    if start_fact and start_fact["verification_status"] == VerificationStatus.verified.value and start_fact["value"]:
        start_date = _date.fromisoformat(start_fact["value"])
        if end_fact and end_fact["verification_status"] == VerificationStatus.verified.value and end_fact["value"]:
            as_of = _date.fromisoformat(end_fact["value"])
            as_of_label = f"custody end date {as_of.isoformat()}"
        else:
            as_of = generated_at.date()
            as_of_label = f"report generation date {as_of.isoformat()} (custody end date not recorded as verified)"
        duration_text = f"{(as_of - start_date).days} day(s) as of {as_of_label}."

    timeline_rows = [
        ["Field", "Value", "Verification Status"],
        _date_row("Custody Start Date", start_fact),
        _date_row("Custody End Date", end_fact),
        ["Custody Duration (for display only — not a legal-threshold calculation)", duration_text, ""],
    ]
    story.append(_table(timeline_rows, [0.33, 0.45, 0.22], s["cell"]))
    story.append(Spacer(1, 8))

    # --- 3. Facts on record ------------------------------------------------
    story.append(_p("3. Facts on Record", s["h2"]))
    story.append(
        _p(
            "Every value below is shown next to its verification status. A value next "
            "to UNVERIFIED, UNKNOWN, or CONFLICT is a candidate only — it is not "
            "established and must not be relied on as confirmed.",
            s["small"],
        )
    )
    story.append(Spacer(1, 4))
    fact_rows = [["Fact", "Value", "Status", "Source", "Reviewed By"]]
    for fact_type in FactType:
        f = facts_by_type.get(fact_type.value)
        label = _FACT_LABELS.get(fact_type.value, fact_type.value)
        if f is None:
            fact_rows.append([label, "— no document uploaded —", _STATUS_LABELS["unknown"], "", ""])
            continue
        source = ""
        if f["source_filename"]:
            source = f["source_filename"] + (f", p.{f['source_page']}" if f["source_page"] else "")
        value_text = _fact_value_text(f["value"])
        if f["verification_status"] == VerificationStatus.conflict.value and f["verification_note"]:
            value_text += f" [CONFLICT NOTE: {f['verification_note']}]"
        fact_rows.append(
            [
                label,
                value_text,
                _STATUS_LABELS.get(f["verification_status"], f["verification_status"]),
                source,
                f["reviewed_by"] or "",
            ]
        )
    story.append(_table(fact_rows, [0.22, 0.26, 0.23, 0.19, 0.10], s["cell"]))
    story.append(Spacer(1, 8))

    # --- 4. Legal rule evaluation ------------------------------------------------
    story.append(_p("4. Legal Rule Evaluation — Section 479 BNSS", s["h2"]))
    if latest_eval is None:
        story.append(
            _p(
                "No Section 479 BNSS evaluation has been performed for this case. This "
                "report includes no legal-threshold calculation. A reviewer can run one "
                "from the case's detail page in the dashboard.",
                s["note"],
            )
        )
    else:
        eval_rows = [
            ["Field", "Value"],
            ["Outcome", latest_eval["outcome"]],
            ["Rule Version", latest_eval["rule_version"]],
            ["Evaluated At", latest_eval["created_at"]],
            ["Reviewer", latest_eval["reviewer"]],
            ["As-of Date", latest_eval["as_of_date"]],
        ]
        story.append(_table(eval_rows, [0.32, 0.68], s["cell"]))
        story.append(Spacer(1, 6))
        story.append(_p(_esc(latest_eval["explanation"]), s["body"]))
        story.append(Spacer(1, 6))

        calc = latest_eval.get("calculation") or {}
        if calc:
            calc_rows = [["Calculation Input/Output", "Value (days unless noted)"]]
            calc_rows.extend([k.replace("_", " "), str(v)] for k, v in calc.items())
            story.append(_table(calc_rows, [0.5, 0.5], s["cell"]))
            story.append(Spacer(1, 6))
        else:
            story.append(
                _p("No calculation was performed — this evaluation was blocked before any threshold math.", s["small"])
            )
            story.append(Spacer(1, 6))

        trace_rows = [["Rule", "Result", "Detail"]]
        trace_rows.extend([t["rule"], t["result"], t["detail"]] for t in latest_eval.get("trace") or [])
        story.append(_table(trace_rows, [0.26, 0.13, 0.61], s["cell"]))
    story.append(Spacer(1, 8))

    # --- 5. Outstanding issues --------------------------------------------------
    story.append(_p("5. Outstanding Issues", s["h2"]))
    issues: list[str] = []
    for fact_type in FactType:
        f = facts_by_type.get(fact_type.value)
        label = _FACT_LABELS.get(fact_type.value, fact_type.value)
        if f is None or f["verification_status"] == VerificationStatus.unknown.value:
            issues.append(f"{label}: missing — no value on record.")
        elif f["verification_status"] == VerificationStatus.unverified.value:
            issues.append(f"{label}: unverified — extracted but not reviewer-confirmed.")
        elif f["verification_status"] == VerificationStatus.conflict.value:
            note = f" Note: {f['verification_note']}" if f["verification_note"] else ""
            issues.append(f"{label}: flagged as conflicting by a reviewer.{note}")
    if latest_eval:
        issues.extend(f"Evaluation blocker: {b}" for b in latest_eval.get("blockers") or [])
        issues.extend(f"Escalated for legal review: {r}" for r in latest_eval.get("escalation_reasons") or [])
    if issues:
        for issue in issues:
            story.append(_p("• " + _esc(issue), s["body"]))
    else:
        story.append(_p("No outstanding issues identified from current records.", s["body"]))
    story.append(Spacer(1, 8))

    # --- 6. Review history --------------------------------------------------
    story.append(_p("6. Review History (Evaluations)", s["h2"]))
    if not evaluations:
        story.append(_p("No evaluations have been run for this case.", s["body"]))
    else:
        hist_rows = [["Evaluated At", "Reviewer", "Rule Version", "Outcome"]]
        hist_rows.extend([ev["created_at"], ev["reviewer"], ev["rule_version"], ev["outcome"]] for ev in evaluations)
        story.append(_table(hist_rows, [0.28, 0.24, 0.22, 0.26], s["cell"]))
    story.append(Spacer(1, 8))

    # --- 7. Sources and limitations --------------------------------------------
    story.append(_p("7. Sources and Limitations", s["h2"]))
    story.append(
        _p(
            "Facts above come from a hand-written keyword/regex heuristic over "
            "uploaded PDFs (optionally OCR'd locally), never from an AI/NLP model and "
            "never sent to any external service. A value is only as reliable as the "
            "status shown next to it in Section 3.",
            s["body"],
        )
    )
    if latest_eval:
        src = latest_eval["statutory_source"]
        gazette_verified = bool(src.get("verified_against_gazette"))
        gazette_label = (
            "VERIFIED against the official Gazette text"
            if gazette_verified
            else "NOT YET VERIFIED against the official Gazette/India Code text — pending legal review"
        )
        story.append(Spacer(1, 4))
        story.append(_p(f"Statutory source status: {_esc(gazette_label)}", s["body"] if gazette_verified else s["note"]))
        story.append(
            _p(
                f"{_esc(src['act'])}, Section {_esc(src['section'])} — “{_esc(src['title'])}” "
                f"(effective {_esc(src['effective_date'])}). Official sources: "
                + ", ".join(_esc(u) for u in src.get("official_sources", [])),
                s["small"],
            )
        )
        story.append(Spacer(1, 4))
        story.append(_p("Implementation and interpretation limitations:", s["body"]))
        for note in (
            "What counts as 'multiple pending cases' under sub-section (2) is a contested "
            "interpretive question — the rule engine escalates it rather than deciding it.",
            "The statutory “year” is converted to a day-count threshold using an "
            "implementation constant (365.25 days/year), not an official legal definition.",
            "Death/life-punishment offences and unresolved escalations require legal review; "
            "this engine makes no determination for them either way.",
        ):
            story.append(_p("• " + note, s["small"]))
    else:
        story.append(
            _p("No evaluation exists for this case, so no statutory source or rule-version information applies yet.", s["small"])
        )
    story.append(Spacer(1, 10))

    # --- 8. Disclaimer (restated in full at the end) ----------------------------
    story.append(_p("8. Disclaimer", s["h2"]))
    story.append(_p(_esc(DISCLAIMER_FULL), s["note"]))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        title=f"Counsel Review Pack - {case['case_id']}",
    )

    def _canvasmaker(*args, **kwargs):
        return _ReviewPackCanvas(*args, case_id=case["case_id"], generated_at_label=generated_at_label, **kwargs)

    doc.build(story, canvasmaker=_canvasmaker)
    return buffer.getvalue()
