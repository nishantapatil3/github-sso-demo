from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes import api, auth


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Sample GitHub SSO", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(api.router)
