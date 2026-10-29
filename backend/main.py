from fastapi import FastAPI

app = FastAPI(title="NyayDrishti API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
