from fastapi import APIRouter, Response


router = APIRouter(tags=["Metrics"])


@router.get("/healthcheck")
def healthcheck() -> dict:
    return {"status": "ok"}
