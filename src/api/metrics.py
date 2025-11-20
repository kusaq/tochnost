from fastapi import APIRouter


router = APIRouter(tags=["Metrics"])


@router.get("/healthcheck")
def healthcheck() -> dict:
    return {"status": "ok"}
