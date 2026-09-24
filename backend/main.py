from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.upload import router as upload_router
from routes.query import router as query_router
from routes.chat import router as chat_router
from chat.database import initialize_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema on startup
    initialize_database()
    yield


app = FastAPI(
    title="HTH2.0 AI Data Analyst API",
    version="2.0.0",
    lifespan=lifespan
)

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


@app.get("/")
def read_root():
    return {"message": "HTH2.0 AI Data Analyst API is active", "status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
