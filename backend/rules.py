"""Deterministic rule engine for Section 479, Bharatiya Nagarik Suraksha
Sanhita (BNSS), 2023 — maximum period for which an undertrial prisoner can be
detained.

This produces an internal REVIEW STATUS only. It is never a bail/release
decision, never a guarantee of any legal outcome, and it never runs on its
own — a reviewer must explicitly trigger each evaluation (see
POST /api/cases/{case_id}/evaluations in main.py). It also never infers or
invents a fact: every critical input must already be reviewer-verified, or
the evaluation is blocked.

ponytail: one hand-checked statutory source and one rule function, not a
generic versioned "rules table" — there is exactly one rule in scope for
this hackathon phase. Upgrade path if a second rule is ever added: pull the
shared bits (critical-fact gating, trace/result shape) into a small
interface, but don't build that ahead of a second real rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from schemas import FactType, VerificationStatus

RULE_VERSION = "bnss-479-v1"

# --- Statutory source -------------------------------------------------------
#
# Text below was captured from a bare-act reproduction (apnilaw.com) cross-checked
# against the structure independently described by multiple legal commentary sources
# (LiveLaw, writinglaw.com, latestlaws.com, advocatemanishjha.com) after the official
# India Code and MHA pages (linked below) refused automated/bot access (HTTP 403).
# NOT independently verified against the Gazette of India or India Code PDF — a human
# reviewer MUST confirm this text against an official copy before this engine is relied
# on for anything beyond an internal review-status flag. See README "Legal review" note.
STATUTORY_SOURCE = {
    "act": "Bharatiya Nagarik Suraksha Sanhita, 2023 (Act No. 46 of 2023)",
    "section": "479",
    "title": "Maximum period for which an undertrial prisoner can be detained",
    "effective_date": "2024-07-01",
    "official_sources": [
        "https://www.indiacode.nic.in/indiacode/handle/123456789/20099",
        "https://www.mha.gov.in/en/commoncontent/new-criminal-laws",
    ],
    "verified_against_gazette": False,
    "text": (
        "(1) Where a person has, during the period of investigation, inquiry or trial "
        "under this Sanhita of an offence under any law (not being an offence for which "
        "the punishment of death or life imprisonment has been specified as one of the "
        "punishments under that law) undergone detention for a period extending up to "
        "one-half of the maximum period of imprisonment specified for that offence under "
        "that law, he shall be released by the Court on bail:\n"
        "Provided that where such person is a first-time offender (who has never been "
        "convicted of any offence in the past) he shall be released on bond by the Court, "
        "if he has undergone detention for the period extending up to one-third of the "
        "maximum period of imprisonment specified for such offence under that law:\n"
        "Provided further that the Court may, after hearing the Public Prosecutor and for "
        "reasons to be recorded by it in writing, order the continued detention of such "
        "person for a period longer than one-half of the said period or release him on "
        "bail bond instead of his bond:\n"
        "Provided also that no such person shall in any case be detained during the "
        "period of investigation, inquiry or trial for more than the maximum period of "
        "imprisonment provided for the said offence under that law.\n"
        "Explanation.—In computing the period of detention under this section for "
        "granting bail, the period of detention passed due to delay in proceeding caused "
        "by the accused shall be excluded.\n"
        "(2) Notwithstanding anything in sub-section (1), and subject to the third "
        "proviso thereof, where an investigation, inquiry or trial in more than one "
        "offence or in multiple cases are pending against a person, he shall not be "
        "released on bail by the Court.\n"
        "(3) The Superintendent of jail, where the accused person is detained, on "
        "completion of one-half or one-third of the period mentioned in sub-section (1), "
        "as the case may be, shall forthwith make an application in writing to the Court "
        "to proceed under sub-section (1) for the release of such person on bail."
    ),
}

# Implementation assumption, not statutory text: converts an approximate statutory
# "N years" maximum sentence into a day-count threshold. The custody side of the
# comparison is always real calendar days (date subtraction), so leap years are
# already handled correctly there — this constant only scales the (already
# approximate) statutory duration input. Flagged for legal review in the README.
DAYS_PER_YEAR = 365.25

# Every one of these must be reviewer-`verified` before any evaluation can run.
# "Do not infer missing facts or treat unverified facts as established."
CRITICAL_FACTS = (
    FactType.custody_start_date,
    FactType.max_punishment_years,
    FactType.death_or_life_punishment,
    FactType.exception_flags,
    FactType.other_pending_cases,
)


@dataclass
class RuleTrace:
    rule: str
    result: str  # "pass" | "fail" | "blocked" | "escalated" | "n/a"
    detail: str


@dataclass
class EvaluationResult:
    outcome: str  # schemas.EvaluationOutcome value
    rule_version: str
    statutory_source: dict
    as_of_date: str
    inputs: dict
    calculation: dict
    trace: list[RuleTrace]
    blockers: list[str]
    escalation_reasons: list[str]
    explanation: str

    def to_dict(self) -> dict:
        return asdict(self)


def _fact(facts_by_type: dict[str, dict], fact_type: FactType) -> dict | None:
    return facts_by_type.get(fact_type.value)


def _unusable_reason(fact: dict | None) -> str | None:
    if fact is None or fact["verification_status"] == VerificationStatus.unknown.value:
        return "missing — no value on record"
    if fact["verification_status"] == VerificationStatus.unverified.value:
        return "unverified — extracted but not reviewer-confirmed"
    if fact["verification_status"] == VerificationStatus.conflict.value:
        return "flagged as conflicting by a reviewer"
    return None  # verified -> usable


def _blocked(as_of_date: date, blockers: list[str]) -> EvaluationResult:
    return EvaluationResult(
        outcome="BLOCKED_MISSING_FACTS",
        rule_version=RULE_VERSION,
        statutory_source=STATUTORY_SOURCE,
        as_of_date=as_of_date.isoformat(),
        inputs={},
        calculation={},
        trace=[RuleTrace(
            "critical_facts_verified", "blocked",
            "One or more facts required by Section 479 are missing, unverified, or conflicting.",
        )],
        blockers=blockers,
        escalation_reasons=[],
        explanation=(
            "Evaluation cannot proceed — " + "; ".join(blockers) + ". "
            "Verify these facts on the case's Document Facts panel, then re-run the evaluation."
        ),
    )


def evaluate_section_479(facts_by_type: dict[str, dict], as_of_date: date) -> EvaluationResult:
    """Pure function: given this case's current facts (fact_type -> fact dict,
    as returned by database.list_facts) and today's date, return a Section 479
    evaluation. Never touches the database — callers persist the result."""

    blockers = [
        f"{ft.value}: {reason}"
        for ft in CRITICAL_FACTS
        if (reason := _unusable_reason(_fact(facts_by_type, ft)))
    ]
    if blockers:
        return _blocked(as_of_date, blockers)

    death_or_life = bool(_fact(facts_by_type, FactType.death_or_life_punishment)["value"])
    custody_start = date.fromisoformat(_fact(facts_by_type, FactType.custody_start_date)["value"])
    max_years = float(_fact(facts_by_type, FactType.max_punishment_years)["value"])
    exception_flags = _fact(facts_by_type, FactType.exception_flags)["value"] or []
    other_pending = _fact(facts_by_type, FactType.other_pending_cases)["value"] or []
    first_time_offender = any("first-time offender" == f.strip().lower() for f in exception_flags)

    custody_end = _fact(facts_by_type, FactType.custody_end_date)
    if custody_end and custody_end["verification_status"] == VerificationStatus.verified.value and custody_end["value"]:
        effective_as_of = date.fromisoformat(custody_end["value"])
    else:
        effective_as_of = as_of_date

    delay_fact = _fact(facts_by_type, FactType.accused_caused_delay_days)
    delay_days = 0
    delay_detail = "No verified accused-caused-delay fact on record; full custody period counted."
    if delay_fact and delay_fact["verification_status"] == VerificationStatus.verified.value and delay_fact["value"] is not None:
        delay_days = int(delay_fact["value"])
        delay_detail = f"{delay_days} day(s) of accused-caused delay excluded, per the Explanation to Section 479(1)."

    custody_days_raw = (effective_as_of - custody_start).days
    custody_days_effective = max(0, custody_days_raw - delay_days)

    calculation = {
        "custody_days_raw": custody_days_raw,
        "accused_caused_delay_days_excluded": delay_days,
        "custody_days_effective": custody_days_effective,
        "half_threshold_days": round(max_years * DAYS_PER_YEAR / 2),
        "third_threshold_days": round(max_years * DAYS_PER_YEAR / 3),
        "max_detention_days": round(max_years * DAYS_PER_YEAR),
    }
    inputs = {
        "custody_start_date": custody_start.isoformat(),
        "as_of_date": effective_as_of.isoformat(),
        "max_punishment_years": max_years,
        "death_or_life_punishment": death_or_life,
        "first_time_offender": first_time_offender,
        "other_pending_cases": other_pending,
    }

    trace = [
        RuleTrace("critical_facts_verified", "pass", "All facts required by Section 479 are reviewer-verified."),
        RuleTrace("delay_exclusion", "pass" if delay_days else "n/a", delay_detail),
    ]

    if death_or_life:
        trace.append(RuleTrace(
            "death_or_life_exclusion", "escalated",
            "The offence carries death or life imprisonment as one of its punishments — "
            "Section 479(1)'s opening clause excludes such offences from this provision entirely.",
        ))
        return EvaluationResult(
            outcome="ESCALATED_LEGAL_REVIEW", rule_version=RULE_VERSION,
            statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
            inputs=inputs, calculation=calculation, trace=trace, blockers=[],
            escalation_reasons=["Offence carries death or life imprisonment (Section 479(1) opening exclusion)."],
            explanation=(
                "Section 479(1) does not apply to offences carrying death or life imprisonment. "
                "This case requires legal review for any other applicable relief; this engine "
                "makes no determination either way."
            ),
        )
    trace.append(RuleTrace("death_or_life_exclusion", "pass", "Offence does not carry death or life imprisonment."))

    if custody_days_effective >= calculation["max_detention_days"]:
        trace.append(RuleTrace(
            "outer_cap_third_proviso", "fail",
            f"Custody ({custody_days_effective}d) has reached the absolute statutory cap "
            f"({calculation['max_detention_days']}d) — the third proviso to Section 479(1), which "
            "applies even where sub-section (2) would otherwise bar release.",
        ))
        return EvaluationResult(
            outcome="REVIEW_THRESHOLD_REACHED", rule_version=RULE_VERSION,
            statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
            inputs=inputs, calculation=calculation, trace=trace, blockers=[], escalation_reasons=[],
            explanation=(
                f"Custody of {custody_days_effective} day(s) has reached the absolute maximum "
                f"detention period of {calculation['max_detention_days']} day(s) under the third "
                "proviso to Section 479(1), which overrides the sub-section (2) bar on multiple "
                "pending cases. This is an internal review-status flag, not a release order."
            ),
        )

    if other_pending:
        trace.append(RuleTrace(
            "multiple_pending_cases_bar", "escalated",
            f"{len(other_pending)} other pending case(s)/offence(s) on record trigger sub-section (2) "
            "(subject to the third proviso, not reached here). What counts as 'multiple cases' under "
            "sub-section (2) is a contested interpretive question — routed to legal review rather "
            "than decided automatically.",
        ))
        return EvaluationResult(
            outcome="ESCALATED_LEGAL_REVIEW", rule_version=RULE_VERSION,
            statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
            inputs=inputs, calculation=calculation, trace=trace, blockers=[],
            escalation_reasons=[f"{len(other_pending)} other pending case(s)/offence(s) on record: {other_pending}."],
            explanation=(
                "Other pending cases/offences are on record. Section 479(2) bars release while "
                "multiple cases are pending (subject to the third proviso, not triggered here). "
                "Whether these specific other cases count as 'multiple cases' under sub-section (2) "
                "is a legal interpretation question — escalated rather than decided automatically."
            ),
        )
    trace.append(RuleTrace("multiple_pending_cases_bar", "pass", "No other pending cases/offences on record."))

    if custody_days_effective >= calculation["half_threshold_days"]:
        trace.append(RuleTrace(
            "one_half_threshold", "fail",
            f"Custody ({custody_days_effective}d) has reached one-half of the maximum punishment "
            f"({calculation['half_threshold_days']}d).",
        ))
        return EvaluationResult(
            outcome="REVIEW_THRESHOLD_REACHED", rule_version=RULE_VERSION,
            statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
            inputs=inputs, calculation=calculation, trace=trace, blockers=[], escalation_reasons=[],
            explanation=(
                f"Custody of {custody_days_effective} day(s) has reached one-half of the maximum "
                f"punishment ({calculation['half_threshold_days']} days) under Section 479(1). This "
                "is an internal review-status flag for a reviewer to act on — not a release order."
            ),
        )

    if custody_days_effective >= calculation["third_threshold_days"]:
        if first_time_offender:
            trace.append(RuleTrace(
                "one_third_threshold_first_time_offender", "fail",
                f"Custody ({custody_days_effective}d) has reached one-third of the maximum "
                f"punishment ({calculation['third_threshold_days']}d) and the accused is a "
                "reviewer-verified first-time offender (first proviso to Section 479(1)).",
            ))
            return EvaluationResult(
                outcome="REVIEW_THRESHOLD_REACHED", rule_version=RULE_VERSION,
                statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
                inputs=inputs, calculation=calculation, trace=trace, blockers=[], escalation_reasons=[],
                explanation=(
                    f"Custody of {custody_days_effective} day(s) has reached one-third of the "
                    f"maximum punishment ({calculation['third_threshold_days']} days). As a verified "
                    "first-time offender, the first proviso to Section 479(1) applies. This is an "
                    "internal review-status flag — not a release order."
                ),
            )
        trace.append(RuleTrace(
            "one_third_threshold_first_time_offender", "n/a",
            "Custody has reached one-third of the maximum punishment, but the accused is confirmed "
            "not a first-time offender, so the first proviso does not apply.",
        ))

    trace.append(RuleTrace("threshold_not_reached", "pass", "No applicable Section 479(1) threshold has been reached yet."))
    return EvaluationResult(
        outcome="THRESHOLD_NOT_REACHED", rule_version=RULE_VERSION,
        statutory_source=STATUTORY_SOURCE, as_of_date=as_of_date.isoformat(),
        inputs=inputs, calculation=calculation, trace=trace, blockers=[], escalation_reasons=[],
        explanation=(
            f"Custody of {custody_days_effective} day(s) has not yet reached the applicable Section "
            f"479(1) threshold ({calculation['third_threshold_days']} days for a verified first-time "
            f"offender, otherwise {calculation['half_threshold_days']} days)."
        ),
    )
