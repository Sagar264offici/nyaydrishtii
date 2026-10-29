from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from database import compute_metrics, get_case, init_db, list_cases
from schemas import Case, Metrics, ReviewStatus


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="NyayDrishti API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
