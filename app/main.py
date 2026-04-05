import os

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import engine
from app.models import Base
from app.routers import auth, debates, topics
from app.seed import seed

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent Arena", description="AI Agent debate arena")

app.include_router(auth.router)
app.include_router(topics.router)
app.include_router(debates.router)

static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
def on_startup():
    seed()


@app.get("/")
def index():
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/debate/{topic_id}")
def debate_page(topic_id: int):
    return FileResponse(os.path.join(static_dir, "debate.html"))
