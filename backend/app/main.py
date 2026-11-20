from fastapi import FastAPI

from .routers.admin_auth import router as admin_auth_router
from .routers.admin_collections import router as admin_collections_router
from .routers.admin_images import router as admin_images_router
from .routers.admin_products import router as admin_products_router
from .routers.admin_settings import router as admin_settings_router
from .routers.admin_variants import router as admin_variants_router
from .routers.public import router as public_router

app = FastAPI(title="Crochet by Carlen")

app.include_router(admin_auth_router)
app.include_router(admin_collections_router)
app.include_router(admin_products_router)
app.include_router(admin_images_router)
app.include_router(admin_variants_router)
app.include_router(admin_settings_router)
app.include_router(public_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
