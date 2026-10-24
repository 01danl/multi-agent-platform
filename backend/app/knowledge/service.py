"""Knowledge base service: storage, ingestion pipeline, retrieval.

Ingestion: upload -> validate -> parse -> chunk -> embed -> store; runs as a
background task in the single server process, updating document.status so the
UI can poll. Retrieval: cosine similarity over chunk embeddings in SQLite —
deliberately small-scale (fine to ~tens of thousands of chunks); Qdrant is
the later adapter behind `KnowledgeStore.search`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import DocumentChunk, KnowledgeBase, KnowledgeDocument
from app.knowledge.embeddings import EmbeddingProvider, build_embedding_provider
from app.knowledge.ingestion import chunk_text, parse_document


def _as_uuid(value: UUID | str) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


@dataclass(frozen=True)
class RetrievedChunk:
    document_id: UUID
    filename: str
    chunk_index: int
    content: str
    score: float


class KnowledgeStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        embedding_provider: EmbeddingProvider | None = None,
        settings=None,
    ) -> None:
        self._sessions = session_factory
        self._settings = settings
        self._embeddings = embedding_provider

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        if self._embeddings is None:
            from app.config import get_settings

            self._embeddings = build_embedding_provider(self._settings or get_settings())
        return self._embeddings

    # ------------------------------------------------------------ knowledge bases

    async def create_kb(self, *, owner_id: UUID | str, name: str, description: str = "") -> KnowledgeBase:
        async with self._sessions() as session:
            kb = KnowledgeBase(owner_id=_as_uuid(owner_id), name=name.strip(), description=description.strip())
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
            return kb

    async def list_kbs(self, *, owner_id: UUID | str) -> list[KnowledgeBase]:
        async with self._sessions() as session:
            stmt = (
                select(KnowledgeBase)
                .where(KnowledgeBase.owner_id == _as_uuid(owner_id))
                .order_by(KnowledgeBase.created_at.desc())
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_kb(self, *, owner_id: UUID | str, kb_id: UUID | str) -> KnowledgeBase | None:
        async with self._sessions() as session:
            kb = await session.get(KnowledgeBase, _as_uuid(kb_id))
            if kb is None or kb.owner_id != _as_uuid(owner_id):
                return None
            return kb

    async def delete_kb(self, *, owner_id: UUID | str, kb_id: UUID | str) -> bool:
        async with self._sessions() as session:
            kb = await session.get(KnowledgeBase, _as_uuid(kb_id))
            if kb is None or kb.owner_id != _as_uuid(owner_id):
                return False
            await session.delete(kb)
            await session.commit()
            return True

    # ----------------------------------------------------------------- documents

    async def list_documents(self, *, owner_id: UUID | str, kb_id: UUID | str) -> list[KnowledgeDocument]:
        async with self._sessions() as session:
            stmt = (
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.kb_id == _as_uuid(kb_id),
                    KnowledgeDocument.owner_id == _as_uuid(owner_id),
                )
                .order_by(KnowledgeDocument.created_at.desc())
            )
            return list((await session.execute(stmt)).scalars().all())

    async def ingest_document(
        self,
        *,
        owner_id: UUID | str,
        kb_id: UUID | str,
        filename: str,
        data: bytes,
        mime_type: str,
    ) -> KnowledgeDocument:
        """Create the document row and process it inline (Phase 2 MVP).

        Single-process friendly: the HTTP handler runs this in a background
        task; status transitions are visible through the API.
        """
        owner_id, kb_id = _as_uuid(owner_id), _as_uuid(kb_id)
        async with self._sessions() as session:
            document = KnowledgeDocument(
                id=uuid4(),
                kb_id=kb_id,
                owner_id=owner_id,
                filename=filename,
                mime_type=mime_type,
                size_bytes=len(data),
                status="processing",
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)

        try:
            parsed = parse_document(data, filename, mime_type)
            chunks = chunk_text(parsed.text)
            if not chunks:
                raise ValueError("Document contains no extractable text")

            embeddings = await self.embedding_provider.embed_documents(chunks)

            async with self._sessions() as session:
                for index, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                    session.add(
                        DocumentChunk(
                            document_id=document.id,
                            kb_id=kb_id,
                            chunk_index=index,
                            content=content,
                            embedding=embedding,
                        )
                    )
                doc = await session.get(KnowledgeDocument, document.id)
                assert doc is not None
                doc.status = "ready"
                doc.chunk_count = len(chunks)
                doc.error = None
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
                return doc
        except Exception as exc:
            async with self._sessions() as session:
                doc = await session.get(KnowledgeDocument, document.id)
                if doc is not None:
                    doc.status = "failed"
                    doc.error = str(exc)[:1000]
                    session.add(doc)
                    await session.commit()
            raise

    async def delete_document(self, *, owner_id: UUID | str, document_id: UUID | str) -> bool:
        async with self._sessions() as session:
            doc = await session.get(KnowledgeDocument, _as_uuid(document_id))
            if doc is None or doc.owner_id != _as_uuid(owner_id):
                return False
            await session.delete(doc)
            await session.commit()
            return True

    # ----------------------------------------------------------------- retrieval

    async def search(
        self,
        *,
        owner_id: UUID | str,
        kb_ids: list[UUID | str],
        query: str,
        limit: int = 4,
    ) -> list[RetrievedChunk]:
        owner_uuid = _as_uuid(owner_id)
        kb_uuids = [_as_uuid(kb) for kb in kb_ids]
        query_embedding = await self.embedding_provider.embed_query(query)

        async with self._sessions() as session:
            stmt = (
                select(DocumentChunk, KnowledgeDocument.filename)
                .join(KnowledgeDocument, KnowledgeDocument.id == DocumentChunk.document_id)
                .where(
                    DocumentChunk.kb_id.in_(kb_uuids),
                    KnowledgeDocument.owner_id == owner_uuid,
                    KnowledgeDocument.status == "ready",
                )
            )
            rows = (await session.execute(stmt)).all()

        scored: list[tuple[float, RetrievedChunk]] = []
        for chunk, filename in rows:
            score = _cosine(query_embedding, chunk.embedding or [])
            if score <= 0.05:  # below noise floor for the local provider
                continue
            scored.append(
                (
                    score,
                    RetrievedChunk(
                        document_id=chunk.document_id,
                        filename=filename,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        score=score,
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in scored[:limit]]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
