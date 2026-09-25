from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.upload import router as upload_router
from routes.query import router as query_router
from routes.chat import router as chat_router
from routes.explorer import router as explorer_router
from core.supabase import initialize_supabase_database
from auth import AuthContextMiddleware, router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Supabase PostgreSQL database schema on startup
    initialize_supabase_database()

    # Pre-load and warm-up LLM model into GPU VRAM once on application startup
    from llm import get_llm_model_manager
    manager = get_llm_model_manager()
    manager.initialize()
    yield



app = FastAPI(
    title="HTH2.0 AI Data Analyst API",
    version="2.0.0",
    lifespan=lifespan
)
app.add_middleware(AuthContextMiddleware)

# Enable CORS for frontend interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(upload_router)
app.include_router(query_router)
app.include_router(chat_router)
app.include_router(explorer_router)
app.include_router(auth_router)


@app.get("/")
def read_root():
    return {"message": "HTH2.0 AI Data Analyst API is active", "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
