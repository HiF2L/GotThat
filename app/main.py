import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.core.database import init_db, async_session_maker
from app.services.graph.seed_data import seed_initial_knowledge_graph
from app.api.v1.feed import router as feed_router
from app.api.v1.deep_tutor import router as deep_tutor_router
from app.api.v1.tracks import router as tracks_router
from app.api.v1.users import router as users_router
from app.api.ws.deep_stream import router as ws_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("got_it_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing GotIt Backend Orchestrator...")
    # Initialize DB tables
    await init_db()
    # Seed initial curriculum
    async with async_session_maker() as session:
        await seed_initial_knowledge_graph(session)
    logger.info("Knowledge Graph seeded. Backend Orchestrator ready!")
    yield
    logger.info("Shutting down GotIt Backend Orchestrator.")


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend Orchestrator for TikTok/Duolingo Quick Feed + 1-on-1 Deep Tutoring Architecture",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for mobile & web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(feed_router, prefix="/api/v1")
app.include_router(deep_tutor_router, prefix="/api/v1")
app.include_router(tracks_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(ws_router)


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "deep_model": settings.DEEP_MODEL,
        "fast_model": settings.FAST_MODEL,
        "stt_model": settings.STT_MODEL,
        "database": settings.DATABASE_URL.split("://")[0],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
