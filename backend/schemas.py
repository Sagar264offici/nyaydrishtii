from datetime import date
from enum import Enum

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
