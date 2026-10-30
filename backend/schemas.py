from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ReviewStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    reviewed = "reviewed"
    escalated = "escalated"


class Case(BaseModel):
    case_id: str
    custody_start_date: date
    custody_end_date: date | None = None
    charges: list[str]
    review_status: ReviewStatus
    assigned_reviewer: str
    next_follow_up: date | None = None


class Metrics(BaseModel):
    total_cases: int
    status_counts: dict[str, int]
    overdue_follow_ups: int
    follow_up_status_counts: dict[str, int]


class CaseStatusUpdate(BaseModel):
    review_status: ReviewStatus
    reviewer: str  # a supplied label, not an authenticated identity -- see AuditEvent note below


# --- Document upload / fact extraction & verification ---


class FactType(str, Enum):
    custody_start_date = "custody_start_date"
    custody_end_date = "custody_end_date"
    current_charges = "current_charges"
    max_punishment = "max_punishment"
    max_punishment_source = "max_punishment_source"
    other_pending_cases = "other_pending_cases"
    exception_flags = "exception_flags"
    # Structured inputs for the Section 479 rule engine (see rules.py). These are
    # reviewer-verified facts like any other — extraction may suggest a candidate,
    # but the engine only ever reads the verified value.
    max_punishment_years = "max_punishment_years"  # numeric max imprisonment term, in years
    death_or_life_punishment = "death_or_life_punishment"  # bool: is death/life one of the punishments
    accused_caused_delay_days = "accused_caused_delay_days"  # int days excluded under the Explanation


class ExtractionMethod(str, Enum):
    text = "text"
    ocr = "ocr"
    unavailable = "unavailable"  # no text layer AND OCR not available
    manual = "manual"  # reserved, not produced by extraction itself


class VerificationStatus(str, Enum):
    unknown = "unknown"  # extraction found nothing for this fact_type
    unverified = "unverified"  # a candidate value was extracted, not yet reviewed
    verified = "verified"  # a human reviewer confirmed it
    conflict = "conflict"  # a human reviewer flagged it as uncertain/conflicting


class Fact(BaseModel):
    id: int
    case_id: str
    fact_type: FactType
    value: Any = None
    original_value: Any = None
    source_filename: str | None = None
    source_page: int | None = None
    extraction_method: ExtractionMethod
    verification_status: VerificationStatus
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    verification_note: str | None = None


class DocumentPreviewResponse(BaseModel):
    filename: str
    case_id: str
    page_count: int
    extraction_method: ExtractionMethod
    message: str | None = None
    facts: list[Fact]


class FactUpdate(BaseModel):
    value: Any | None = None
    verification_status: VerificationStatus | None = None
    reviewer: str | None = None
    verification_note: str | None = None


# --- Section 479 BNSS rule-engine evaluations ---
# Internal review-status flags only. Never a bail/release decision or a
# guarantee of any legal outcome — see backend/rules.py and the README.


class EvaluationOutcome(str, Enum):
    review_threshold_reached = "REVIEW_THRESHOLD_REACHED"
    threshold_not_reached = "THRESHOLD_NOT_REACHED"
    blocked_missing_facts = "BLOCKED_MISSING_FACTS"
    escalated_legal_review = "ESCALATED_LEGAL_REVIEW"


class RuleTraceEntry(BaseModel):
    rule: str
    result: str
    detail: str


class Evaluation(BaseModel):
    id: int
    case_id: str
    created_at: str
    reviewer: str
    rule_version: str
    outcome: EvaluationOutcome
    statutory_source: dict
    as_of_date: str
    inputs: dict
    calculation: dict
    trace: list[RuleTraceEntry]
    blockers: list[str]
    escalation_reasons: list[str]
    explanation: str
    facts_snapshot: list[Fact]


class EvaluationRequest(BaseModel):
    reviewer: str


# --- Follow-up tasks ---


class FollowUpStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class FollowUp(BaseModel):
    id: int
    case_id: str
    title: str
    description: str | None = None
    assigned_reviewer: str
    due_at: str  # ISO 8601 datetime, always normalized to UTC before storage
    status: FollowUpStatus
    created_at: str
    updated_at: str
    completed_at: str | None = None
    completed_by: str | None = None
    is_overdue: bool  # computed fresh on every read: due_at < now AND not completed/cancelled


class FollowUpCreate(BaseModel):
    case_id: str
    title: str
    description: str | None = None
    assigned_reviewer: str
    due_at: datetime  # accepts any ISO 8601 datetime, naive or offset-aware


class FollowUpUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    assigned_reviewer: str | None = None
    due_at: datetime | None = None
    status: FollowUpStatus | None = None
    # The reviewer performing THIS edit -- required when completing or cancelling
    # (so completed_by is known), optional otherwise. A supplied label, not an
    # authenticated identity -- see AuditEvent note below.
    reviewer: str | None = None


# --- Audit trail ---
#
# Append-only: there is deliberately no update/delete function for this log.
# `actor` throughout this file (here, and on Fact.reviewed_by, Evaluation.reviewer,
# FollowUp.assigned_reviewer/completed_by) is a free-text label the client supplied
# -- this application has no login/authentication, so it is never a verified
# identity. Nothing in this codebase should treat it as one.


class AuditEventType(str, Enum):
    fact_verified = "fact_verified"
    fact_corrected = "fact_corrected"
    fact_conflict_flagged = "fact_conflict_flagged"
    fact_conflict_resolved = "fact_conflict_resolved"
    evaluation_run = "evaluation_run"
    case_status_changed = "case_status_changed"
    followup_created = "followup_created"
    followup_updated = "followup_updated"
    followup_reassigned = "followup_reassigned"
    followup_started = "followup_started"
    followup_completed = "followup_completed"
    followup_cancelled = "followup_cancelled"


class AuditEvent(BaseModel):
    id: int
    case_id: str
    event_type: AuditEventType
    entity_id: str | None = None
    actor: str | None = None
    description: str
    before: dict | None = None
    after: dict | None = None
    created_at: str
