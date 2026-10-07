from fastapi import FastAPI

app = FastAPI(
    title="StudyMate API",
    description="RAG-based study assistant with cited answers.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}