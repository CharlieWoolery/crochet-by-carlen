from fastapi import FastAPI

from .routers.admin_auth import router as admin_auth_router

app = FastAPI(title="Crochet by Carlen")

app.include_router(admin_auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
