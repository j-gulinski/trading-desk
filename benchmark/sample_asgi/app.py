import asyncio
import itertools
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from books_service.config import SERVICE_NAME
from books_service.schemas import book_to_dict
from desk_domain.audit import write_audit
from desk_domain.models import Book
from desk_runtime.config import DATABASE_MAX_OVERFLOW, DATABASE_POOL_SIZE, env_required
from desk_runtime.functions import utcnow
from desk_runtime.serialization import to_json
from sample_core import STUB_URL, call_stub, cpu_work, new_book, write_then_read

engine = create_async_engine(
    env_required("DATABASE_URL"), pool_pre_ping=True, json_serializer=to_json,
    pool_size=DATABASE_POOL_SIZE, max_overflow=DATABASE_MAX_OVERFLOW,
)
AsyncSession = async_sessionmaker(engine)


@asynccontextmanager
async def lifespan(app):
    app.state.stub = httpx.AsyncClient(timeout=5)
    yield
    await app.state.stub.aclose()
    await engine.dispose()


app = FastAPI(lifespan=lifespan)
sync_app = FastAPI()


def json_response(data):
    return Response(to_json(data), media_type="application/json")


async def write_then_read_async():
    fields, book_id, now = new_book(), uuid.uuid4(), utcnow()
    async with AsyncSession.begin() as session:
        book = Book(book_id=book_id, **fields, is_active=True, created_at=now, updated_at=now)
        session.add(book)
        await session.flush()
        write_audit(SERVICE_NAME, "BOOK_CREATED", f"Book {book.name} created",
                    entity_type="BOOK", entity_id=book_id, session=session)
    async with AsyncSession.begin() as session:
        return book_to_dict(await session.get(Book, book_id))


@app.get("/health")
async def health():
    return json_response({"status": "ok"})


@app.get("/io")
async def io():
    reply = await app.state.stub.get(STUB_URL)
    return json_response({"downstream": reply.json()})


@app.get("/cpu")
async def cpu():
    return json_response({"digest": cpu_work()})


@app.post("/db")
async def db():
    return json_response(await write_then_read_async())


@app.get("/stream")
async def stream():
    async def events():
        for n in itertools.count():
            yield f"data: {n}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        events(), headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
    )


@sync_app.get("/health")
def health_sync():
    return json_response({"status": "ok"})


@sync_app.get("/io")
def io_sync():
    return json_response({"downstream": call_stub()})


@sync_app.get("/cpu")
def cpu_sync():
    return json_response({"digest": cpu_work()})


@sync_app.post("/db")
def db_sync():
    return json_response(write_then_read())
