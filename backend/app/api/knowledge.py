"""Knowledge base endpoints: KB CRUD, document upload/list/delete.

Uploads: multipart, validated (extension/MIME whitelist, size cap from
settings), ingested in a background task of the single server process;
clients poll document status until ready/failed.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, UploadFile, status

from app.api.deps import CurrentSession, CurrentUser
from app.api.schemas import DocumentOut, KbCreate, KbOut
from app.db.models import KnowledgeBase, KnowledgeDocument
from app.knowledge.ingestion import SUPPORTED_EXTENSIONS, detect_kind

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _store(request: Request):
    from app.knowledge.service import KnowledgeStore

    store = getattr(request.app.state, "knowledge_store", None)
    if not isinstance(store, KnowledgeStore):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Knowledge store unavailable")
    return store


async def _owned_kb(kb_id: UUID, user, db) -> KnowledgeBase:
    kb = await db.get(KnowledgeBase, kb_id)
    if kb is None or kb.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found")
    return kb


@router.get("", response_model=list[KbOut])
async def list_kbs(user: CurrentUser, request: Request) -> list[KbOut]:
    kbs = await _store(request).list_kbs(owner_id=user.id)
    return [KbOut.model_validate(kb) for kb in kbs]


@router.post("", response_model=KbOut, status_code=status.HTTP_201_CREATED)
async def create_kb(body: KbCreate, user: CurrentUser, request: Request) -> KbOut:
    kb = await _store(request).create_kb(owner_id=user.id, name=body.name, description=body.description)
    return KbOut.model_validate(kb)


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb(kb_id: UUID, user: CurrentUser, db: CurrentSession, request: Request) -> None:
    if not await _store(request).delete_kb(owner_id=user.id, kb_id=kb_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found")


@router.get("/{kb_id}/documents", response_model=list[DocumentOut])
async def list_documents(
    kb_id: UUID, user: CurrentUser, db: CurrentSession, request: Request
) -> list[DocumentOut]:
    await _owned_kb(kb_id, user, db)
    docs = await _store(request).list_documents(owner_id=user.id, kb_id=kb_id)
    return [DocumentOut.model_validate(d) for d in docs]


@router.post("/{kb_id}/documents", response_model=DocumentOut, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    kb_id: UUID,
    user: CurrentUser,
    db: CurrentSession,
    request: Request,
    background: BackgroundTasks,
    file: UploadFile,
) -> DocumentOut:
    from app.config import get_settings

    await _owned_kb(kb_id, user, db)
    settings = get_settings()

    filename = file.filename or "untitled"
    if detect_kind(filename, file.content_type or "") is None:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unsupported file type. Allowed: {allowed}")

    data = await file.read()
    if len(data) > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File exceeds the {settings.max_upload_size_mb} MB limit",
        )

    store = _store(request)
    document = KnowledgeDocument(
        kb_id=kb_id,
        owner_id=user.id,
        filename=filename,
        mime_type=file.content_type or "text/plain",
        size_bytes=len(data),
        status="pending",
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    background.add_task(
        _ingest_task,
        store,
        owner_id=user.id,
        kb_id=kb_id,
        document_id=document.id,
        filename=filename,
        data=data,
        mime_type=document.mime_type,
    )
    return DocumentOut.model_validate(document)


@router.delete("/{kb_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    kb_id: UUID, document_id: UUID, user: CurrentUser, db: CurrentSession, request: Request
) -> None:
    await _owned_kb(kb_id, user, db)
    if not await _store(request).delete_document(owner_id=user.id, document_id=document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")


async def _ingest_task(store, *, owner_id, kb_id, document_id, filename, data, mime_type) -> None:
    """Background ingestion: parse/chunk/embed and update the document row.

    Failures are recorded on the row (status=failed + error) so the UI can
    show why a document did not become searchable.
    """
    from app.knowledge.ingestion import chunk_text, parse_document

    try:
        parsed = parse_document(data, filename, mime_type)
        chunks = chunk_text(parsed.text)
        if not chunks:
            raise ValueError("Document contains no extractable text")
        embeddings = await store.embedding_provider.embed_documents(chunks)

        from app.db.models import DocumentChunk

        sessions = store._sessions  # noqa: SLF001 — same component family
        async with sessions() as session:
            for index, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                session.add(
                    DocumentChunk(
                        document_id=document_id,
                        kb_id=kb_id,
                        chunk_index=index,
                        content=content,
                        embedding=embedding,
                    )
                )
            doc = await session.get(KnowledgeDocument, document_id)
            assert doc is not None
            doc.status = "ready"
            doc.chunk_count = len(chunks)
            doc.error = None
            session.add(doc)
            await session.commit()
    except Exception as exc:
        sessions = store._sessions  # noqa: SLF001
        async with sessions() as session:
            doc = await session.get(KnowledgeDocument, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error = str(exc)[:1000]
                session.add(doc)
                await session.commit()
