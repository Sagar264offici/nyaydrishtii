import math
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from database import (
    compute_metrics,
    create_follow_up,
    get_case,
    get_fact,
    get_follow_up,
    init_db,
    insert_evaluation,
    list_audit_events,
    list_cases,
    list_evaluations,
    list_facts,
    list_follow_ups,
    update_case_status,
    update_fact,
    update_follow_up,
    upsert_extracted_facts,
)
from extraction import InvalidPDFError, extract_candidate_facts, extract_pages, ocr_available, ocr_pages
from review_pack import generate_review_pack_pdf
from rules import RULE_VERSION, evaluate_section_479
from schemas import (
    AuditEvent,
    AuditEventType,
    Case,
    CaseStatusUpdate,
    DocumentPreviewResponse,
    Evaluation,
    EvaluationRequest,
    Fact,
    FactType,
    FactUpdate,
    ExtractionMethod,
    FollowUp,
    FollowUpCreate,
    FollowUpStatus,
    FollowUpUpdate,
    Metrics,
    ReviewStatus,
    VerificationStatus,
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024

_DATE_FACT_TYPES = {FactType.custody_start_date, FactType.custody_end_date}
_LIST_FACT_TYPES = {FactType.current_charges, FactType.other_pending_cases, FactType.exception_flags}
_STRING_FACT_TYPES = {FactType.max_punishment, FactType.max_punishment_source}
_POSITIVE_NUMBER_FACT_TYPES = {FactType.max_punishment_years}
_NONNEGATIVE_INT_FACT_TYPES = {FactType.accused_caused_delay_days}
_BOOLEAN_FACT_TYPES = {FactType.death_or_life_punishment}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NyayDrishti API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


def _validate_fact_value(fact_type: FactType, value) -> None:
    if fact_type in _DATE_FACT_TYPES:
        if not isinstance(value, str):
            raise HTTPException(422, f"{fact_type.value} must be an ISO date string (YYYY-MM-DD)")
        try:
            date.fromisoformat(value)
        except ValueError:
            raise HTTPException(422, f"{fact_type.value} must be a valid ISO date (YYYY-MM-DD)")
    elif fact_type in _LIST_FACT_TYPES:
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise HTTPException(422, f"{fact_type.value} must be a list of strings")
    elif fact_type in _STRING_FACT_TYPES:
        if not isinstance(value, str):
            raise HTTPException(422, f"{fact_type.value} must be a string")
    elif fact_type in _POSITIVE_NUMBER_FACT_TYPES:
        # math.isfinite() rejects NaN and +/-Infinity -- both pass a bare "value <= 0"
        # check (NaN compares False to everything, inf is not <= 0), and both would
        # otherwise crash round() in rules.py with an uncaught ValueError/OverflowError
        # instead of a clean 422. 200 years is a generous sane upper bound for any
        # finite-term sentence (death/life is its own separate boolean fact).
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not (0 < value <= 200)
        ):
            raise HTTPException(422, f"{fact_type.value} must be a positive, finite number (<= 200)")
    elif fact_type in _NONNEGATIVE_INT_FACT_TYPES:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HTTPException(422, f"{fact_type.value} must be a non-negative whole number")
    elif fact_type in _BOOLEAN_FACT_TYPES:
        if not isinstance(value, bool):
            raise HTTPException(422, f"{fact_type.value} must be true or false")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/cases", response_model=list[Case])
def get_cases(
    status: ReviewStatus | None = Query(None, description="Filter by review status"),
    reviewer: str | None = Query(None, description="Filter by assigned reviewer"),
    q: str | None = Query(None, description="Search case ID, charges, or reviewer"),
):
    return list_cases(status=status.value if status else None, reviewer=reviewer, q=q)


@app.get("/api/cases/{case_id}", response_model=Case)
def get_case_detail(case_id: str):
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return case


@app.get("/api/metrics", response_model=Metrics)
def get_metrics():
    return compute_metrics()


@app.post("/api/documents/preview", response_model=DocumentPreviewResponse)
async def preview_document(case_id: str = Form(...), file: UploadFile = File(...)):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    # Read at most one byte over the limit, so an oversized upload is bounded
    # by MAX_UPLOAD_BYTES in memory rather than being fully buffered before
    # the size check below ever runs.
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    filename = file.filename or ""

    if not filename.lower().endswith(".pdf") or not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds the 10 MB upload limit")

    try:
        pages = extract_pages(content)
    except InvalidPDFError:
        raise HTTPException(
            status_code=422,
            detail="Could not read PDF — the file may be corrupted or empty.",
        )

    message = None
    has_text = any((p or "").strip() for p in pages)
    if has_text:
        method = ExtractionMethod.text
    elif ocr_available():
        pages = ocr_pages(content)
        method = ExtractionMethod.ocr
    else:
        method = ExtractionMethod.unavailable
        message = (
            "No extractable text found and OCR is unavailable on this server. "
            "Please enter facts manually."
        )

    candidates = extract_candidate_facts(pages) if method != ExtractionMethod.unavailable else {}
    upsert_extracted_facts(case_id, filename, method.value, candidates)

    return DocumentPreviewResponse(
        filename=filename,
        case_id=case_id,
        page_count=len(pages),
        extraction_method=method,
        message=message,
        facts=list_facts(case_id),
    )


@app.get("/api/cases/{case_id}/facts", response_model=list[Fact])
def get_case_facts(case_id: str):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return list_facts(case_id)


@app.patch("/api/cases/{case_id}/facts/{fact_id}", response_model=Fact)
def patch_fact(case_id: str, fact_id: int, payload: FactUpdate):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    fact = get_fact(case_id, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"Fact {fact_id} not found for case '{case_id}'")

    fields_set = payload.model_fields_set
    changes: dict = {}

    if "value" in fields_set:
        if payload.value is not None:
            _validate_fact_value(FactType(fact["fact_type"]), payload.value)
        changes["value"] = payload.value

    new_reviewer = payload.reviewer if "reviewer" in fields_set else None
    effective_reviewer = new_reviewer if new_reviewer is not None else fact["reviewed_by"]

    if payload.verification_status in (VerificationStatus.verified, VerificationStatus.conflict):
        if not effective_reviewer:
            raise HTTPException(
                status_code=422,
                detail="A reviewer is required to mark a fact as verified or conflict.",
            )

    if "verification_status" in fields_set and payload.verification_status is not None:
        changes["verification_status"] = payload.verification_status.value
    elif (
        "value" in fields_set
        and payload.value is not None
        and fact["verification_status"] == VerificationStatus.unknown.value
    ):
        # A value was just entered for a fact that had none — "unknown" no longer
        # applies. It's still not reviewer-confirmed, so "unverified", not "verified".
        changes["verification_status"] = VerificationStatus.unverified.value
    if "reviewer" in fields_set:
        changes["reviewed_by"] = new_reviewer
    if "verification_note" in fields_set:
        changes["verification_note"] = payload.verification_note
    if "verification_status" in fields_set or "reviewer" in fields_set:
        changes["reviewed_at"] = datetime.now(timezone.utc).isoformat()

    # Only log an audit event if a SEMANTIC field actually changed -- ignores the
    # reviewed_at bookkeeping timestamp, so a true no-op PATCH (e.g. a retried
    # request, or an explicit-null verification_status) never logs a duplicate.
    semantic_fields = ("value", "verification_status", "reviewed_by", "verification_note")
    diff = {k: v for k, v in changes.items() if k in semantic_fields and v != fact.get(k)}

    audit = None
    if diff:
        new_status = changes.get("verification_status")
        old_status = fact["verification_status"]
        if new_status == VerificationStatus.conflict.value and old_status != VerificationStatus.conflict.value:
            event_type = AuditEventType.fact_conflict_flagged
        elif old_status == VerificationStatus.conflict.value and new_status not in (None, VerificationStatus.conflict.value):
            event_type = AuditEventType.fact_conflict_resolved
        elif new_status == VerificationStatus.verified.value:
            event_type = AuditEventType.fact_verified
        else:
            event_type = AuditEventType.fact_corrected
        audit = {
            "case_id": case_id,
            "event_type": event_type.value,
            "entity_id": str(fact_id),
            "actor": effective_reviewer,
            "description": f"Fact '{fact['fact_type']}' updated ({event_type.value.replace('fact_', '').replace('_', ' ')})",
            "before": {k: fact.get(k) for k in diff},
            "after": diff,
        }

    return update_fact(case_id, fact_id, audit=audit, **changes)


@app.post("/api/cases/{case_id}/evaluations", response_model=Evaluation)
def create_evaluation(case_id: str, payload: EvaluationRequest):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    reviewer = payload.reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=422, detail="A reviewer is required to run an evaluation.")

    facts = list_facts(case_id)
    facts_by_type = {f["fact_type"]: f for f in facts}
    result = evaluate_section_479(facts_by_type, date.today()).to_dict()
    result["facts_snapshot"] = facts

    audit = {
        "case_id": case_id,
        "event_type": AuditEventType.evaluation_run.value,
        "entity_id": None,  # filled in once the new evaluation's id is known
        "actor": reviewer,
        "description": f"Section 479 evaluation run (rule {RULE_VERSION}): {result['outcome']}",
        "before": None,
        "after": {"outcome": result["outcome"], "rule_version": RULE_VERSION},
    }
    return insert_evaluation(case_id, reviewer, RULE_VERSION, result["outcome"], result, audit=audit)


@app.get("/api/cases/{case_id}/evaluations", response_model=list[Evaluation])
def get_case_evaluations(case_id: str):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return list_evaluations(case_id)


@app.get("/api/cases/{case_id}/review-pack")
def get_review_pack(case_id: str):
    """Renders the case's CURRENT recorded state into a PDF. Never runs a new
    Section 479 evaluation -- it only reads the most recent one already on
    file (if any) via list_evaluations, same as every other read here."""
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")

    facts = list_facts(case_id)
    evaluations = list_evaluations(case_id)
    pdf_bytes = generate_review_pack_pdf(case, facts, evaluations, datetime.now(timezone.utc))

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="NyayDrishti-ReviewPack-{case_id}.pdf"'},
    )


@app.patch("/api/cases/{case_id}", response_model=Case)
def patch_case_status(case_id: str, payload: CaseStatusUpdate):
    """The only writable case field is review_status -- custody dates, charges,
    etc. are seed data and stay read-only. `reviewer` is a supplied label, not
    an authenticated identity (this app has no login)."""
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    reviewer = payload.reviewer.strip()
    if not reviewer:
        raise HTTPException(status_code=422, detail="A reviewer is required to change review status.")
    if payload.review_status.value == case["review_status"]:
        return case  # true no-op -- nothing to persist or log

    audit = {
        "case_id": case_id,
        "event_type": AuditEventType.case_status_changed.value,
        "entity_id": case_id,
        "actor": reviewer,
        "description": f"Review status changed from {case['review_status']} to {payload.review_status.value} by {reviewer}",
        "before": {"review_status": case["review_status"]},
        "after": {"review_status": payload.review_status.value},
    }
    return update_case_status(case_id, payload.review_status.value, audit)


def _normalize_due_at(value: datetime) -> str:
    """Normalize any (naive or offset-aware) datetime to a UTC ISO string. A
    naive input is assumed to already be UTC. Comparisons against "now" always
    happen after this normalization, so a due_at given in any timezone is
    compared correctly rather than by raw/local wall-clock numbers."""
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    except (OverflowError, ValueError) as exc:
        # An extreme offset-aware datetime near year 1 or 9999 can overflow
        # when converting to UTC -- a clean 422 beats an uncaught 500.
        raise HTTPException(status_code=422, detail="due_at is outside the representable date range") from exc


@app.post("/api/followups", response_model=FollowUp)
def create_follow_up_endpoint(payload: FollowUpCreate):
    if get_case(payload.case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{payload.case_id}' not found")
    title = payload.title.strip()
    reviewer = payload.assigned_reviewer.strip()
    if not title:
        raise HTTPException(status_code=422, detail="title is required")
    if not reviewer:
        raise HTTPException(status_code=422, detail="assigned_reviewer is required")
    due_at = _normalize_due_at(payload.due_at)

    audit = {
        "case_id": payload.case_id,
        "event_type": AuditEventType.followup_created.value,
        "entity_id": None,  # filled in once the new follow-up's id is known
        "actor": reviewer,
        "description": f"Follow-up '{title}' created, assigned to {reviewer}, due {due_at}",
        "before": None,
        "after": {"title": title, "assigned_reviewer": reviewer, "due_at": due_at, "status": "pending"},
    }
    return create_follow_up(
        case_id=payload.case_id,
        title=title,
        description=payload.description,
        assigned_reviewer=reviewer,
        due_at=due_at,
        audit=audit,
    )


@app.get("/api/followups", response_model=list[FollowUp])
def get_follow_ups_endpoint(
    status: FollowUpStatus | None = Query(None, description="Filter by status"),
    reviewer: str | None = Query(None, description="Filter by assigned reviewer"),
    case_id: str | None = Query(None, description="Filter by case ID"),
    overdue: bool | None = Query(None, description="Filter by overdue state"),
):
    return list_follow_ups(
        status=status.value if status else None, reviewer=reviewer, case_id=case_id, overdue=overdue
    )


@app.get("/api/cases/{case_id}/followups", response_model=list[FollowUp])
def get_case_follow_ups(case_id: str):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return list_follow_ups(case_id=case_id)


@app.patch("/api/followups/{followup_id}", response_model=FollowUp)
def patch_follow_up(followup_id: int, payload: FollowUpUpdate):
    existing = get_follow_up(followup_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Follow-up {followup_id} not found")

    fields_set = payload.model_fields_set
    changes: dict = {}
    before: dict = {}
    after: dict = {}
    reassigned = False
    status_changed = False
    new_status_value = None

    terminal = existing["status"] in (FollowUpStatus.completed.value, FollowUpStatus.cancelled.value)
    if terminal and "status" in fields_set and payload.status is not None and payload.status.value != existing["status"]:
        raise HTTPException(
            status_code=422, detail=f"Cannot change status of a {existing['status']} follow-up."
        )

    if "title" in fields_set and payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="title cannot be empty")
        if title != existing["title"]:
            before["title"], after["title"] = existing["title"], title
            changes["title"] = title

    if "description" in fields_set and payload.description != existing["description"]:
        before["description"], after["description"] = existing["description"], payload.description
        changes["description"] = payload.description

    if "assigned_reviewer" in fields_set and payload.assigned_reviewer is not None:
        new_reviewer_name = payload.assigned_reviewer.strip()
        if not new_reviewer_name:
            raise HTTPException(status_code=422, detail="assigned_reviewer cannot be empty")
        if new_reviewer_name != existing["assigned_reviewer"]:
            before["assigned_reviewer"], after["assigned_reviewer"] = existing["assigned_reviewer"], new_reviewer_name
            changes["assigned_reviewer"] = new_reviewer_name
            reassigned = True

    if "due_at" in fields_set and payload.due_at is not None:
        normalized = _normalize_due_at(payload.due_at)
        if normalized != existing["due_at"]:
            before["due_at"], after["due_at"] = existing["due_at"], normalized
            changes["due_at"] = normalized

    if "status" in fields_set and payload.status is not None and payload.status.value != existing["status"]:
        new_status_value = payload.status.value
        status_changed = True
        before["status"], after["status"] = existing["status"], new_status_value
        changes["status"] = new_status_value
        if new_status_value in (FollowUpStatus.completed.value, FollowUpStatus.cancelled.value):
            actor_name = (payload.reviewer or "").strip()
            if not actor_name:
                raise HTTPException(
                    status_code=422, detail="A reviewer is required to complete or cancel a follow-up."
                )
            changes["completed_at"] = datetime.now(timezone.utc).isoformat()
            changes["completed_by"] = actor_name

    if not changes:
        return existing  # true no-op -- nothing to persist or log

    changes["updated_at"] = datetime.now(timezone.utc).isoformat()
    actor = (payload.reviewer or "").strip() or existing["assigned_reviewer"]

    if status_changed and new_status_value == FollowUpStatus.completed.value:
        event_type = AuditEventType.followup_completed
        description = f"Follow-up '{existing['title']}' marked completed by {actor}"
    elif status_changed and new_status_value == FollowUpStatus.cancelled.value:
        event_type = AuditEventType.followup_cancelled
        description = f"Follow-up '{existing['title']}' cancelled by {actor}"
    elif status_changed and new_status_value == FollowUpStatus.in_progress.value:
        event_type = AuditEventType.followup_started
        description = f"Follow-up '{existing['title']}' started by {actor}"
    elif status_changed:
        event_type = AuditEventType.followup_updated
        description = f"Follow-up '{existing['title']}' status changed from {existing['status']} to {new_status_value}"
    elif reassigned:
        event_type = AuditEventType.followup_reassigned
        description = (
            f"Follow-up '{existing['title']}' reassigned from {before['assigned_reviewer']} "
            f"to {after['assigned_reviewer']}"
        )
    else:
        event_type = AuditEventType.followup_updated
        description = f"Follow-up '{existing['title']}' updated"

    audit = {
        "case_id": existing["case_id"],
        "event_type": event_type.value,
        "entity_id": str(followup_id),
        "actor": actor,
        "description": description,
        "before": before,
        "after": after,
    }
    return update_follow_up(followup_id, changes, audit)


@app.get("/api/cases/{case_id}/audit-log", response_model=list[AuditEvent])
def get_case_audit_log(
    case_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    if get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")
    return list_audit_events(case_id, limit=limit, offset=offset)
