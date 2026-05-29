"""SGarden Inventory API — application entry point."""
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from database import init_indexes
from routes.auth import router as auth_router
from routes.orders import router as orders_router
from routes.products import router as products_router
from routes.users import router as users_router
from seed import seed_data


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Run startup/shutdown hooks around the app lifecycle."""
    await init_indexes()
    await seed_data()
    yield


app = FastAPI(
    title="SGarden API",
    description="Inventory Management API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    """Return a flat dict of field → message for validation errors."""
    errors = {}
    for error in exc.errors():
        loc = error.get("loc", ())
        field = str(loc[-1]) if loc else "unknown"
        ctx = error.get("ctx", {})
        msg = str(ctx["error"]) if "error" in ctx else error["msg"]
        errors[field] = msg
    return JSONResponse(status_code=400, content={"errors": errors})


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(products_router)
app.include_router(users_router)


@app.get("/api/health")
async def health():
    """Liveness check."""
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
