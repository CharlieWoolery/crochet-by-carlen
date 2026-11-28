from fastapi import FastAPI

from .routers.admin_auth import router as admin_auth_router
from .routers.admin_collections import router as admin_collections_router
from .routers.admin_custom_requests import router as admin_custom_requests_router
from .routers.admin_images import router as admin_images_router
from .routers.admin_orders import router as admin_orders_router
from .routers.admin_products import router as admin_products_router
from .routers.admin_settings import router as admin_settings_router
from .routers.admin_variants import router as admin_variants_router
from .routers.custom_requests import router as custom_requests_router
from .routers.orders import router as orders_router
from .routers.public import router as public_router

app = FastAPI(title="Crochet by Carlen")

# All routes live under /api so the Vite dev-server proxy can forward /api/*
# to FastAPI without path rewriting, keeping browser cookies working during dev.
app.include_router(public_router, prefix="/api")
app.include_router(orders_router, prefix="/api")
app.include_router(custom_requests_router, prefix="/api")
app.include_router(admin_auth_router, prefix="/api")
app.include_router(admin_collections_router, prefix="/api")
app.include_router(admin_products_router, prefix="/api")
app.include_router(admin_images_router, prefix="/api")
app.include_router(admin_variants_router, prefix="/api")
app.include_router(admin_settings_router, prefix="/api")
app.include_router(admin_orders_router, prefix="/api")
app.include_router(admin_custom_requests_router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
