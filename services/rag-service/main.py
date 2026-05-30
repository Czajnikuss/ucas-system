# -*- coding: utf-8 -*-
"""
UCAS RAG Service
================
Dedykowana warstwa RAG (Retrieval-Augmented Generation) dla kaskady klasyfikacji.

Zadanie: dla zadanego tekstu zapytania zwrócić najbardziej podobne próbki treningowe
danego kategoryzatora (wyszukiwanie wektorowe pgvector). Wynik jest wstrzykiwany jako
kontekst (few-shot) do promptu warstwy LLM.

Kontrakt `/search` jest celowo zgodny z tym, czego oczekuje `llm-layer`:
    request : {"categorizer_id": <slug|nazwa>, "query_text": <str>, "top_k": <int>}
    response: {"categorizer_id", "query_text", "samples": [{text, category, similarity}], "count"}

Serwis sam generuje embedding zapytania (woła `embeddings-service`), więc klient nie
musi dostarczać gotowego wektora.
"""
import os
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

app = FastAPI(
    title="UCAS RAG Service",
    version="1.1.0",
    description="Wektorowe wyszukiwanie podobnych próbek treningowych (pgvector) jako kontekst RAG dla warstwy LLM.",
    docs_url="/swagger",
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db",
)
EMBEDDINGS_SERVICE_URL = os.getenv("EMBEDDINGS_SERVICE_URL", "http://embeddings-service:8050")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================
# MODELE
# ============================================

class SearchRequest(BaseModel):
    categorizer_id: str          # slug LUB nazwa kategoryzatora
    query_text: str
    top_k: int = 5


class SampleItem(BaseModel):
    text: str
    category: str
    similarity: float


class SearchResponse(BaseModel):
    categorizer_id: str
    query_text: str
    samples: List[SampleItem]
    count: int


class InjectRequest(BaseModel):
    categorizer_id: str          # slug LUB nazwa kategoryzatora
    text: str
    category: str
    embedding: List[float]       # gotowy wektor (np. z embeddings-service)


class InjectResponse(BaseModel):
    status: str
    inserted_id: str


# ============================================
# HELPERY
# ============================================

def resolve_categorizer_uuid(db: Session, categorizer_id: str) -> Optional[str]:
    """Mapuje publiczny slug LUB nazwę kategoryzatora na wewnętrzny UUID z tabeli `categorizers`."""
    row = db.execute(
        text("SELECT id FROM categorizers WHERE categorizer_id = :cid OR name = :cid LIMIT 1"),
        {"cid": categorizer_id},
    ).fetchone()
    return str(row[0]) if row else None


def to_pgvector_literal(embedding: List[float]) -> str:
    """Zamienia listę floatów na literał pgvector w formacie '[v1,v2,...]'."""
    return "[" + ",".join(map(str, embedding)) + "]"


async def embed_query(query_text: str) -> List[float]:
    """Pobiera znormalizowany embedding zapytania z embeddings-service."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{EMBEDDINGS_SERVICE_URL}/embed",
            json={"texts": [query_text], "normalize": True},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Embeddings service error: {resp.status_code}")
    embeddings = resp.json().get("embeddings", [])
    if not embeddings:
        raise HTTPException(status_code=502, detail="Embeddings service returned no vector")
    return embeddings[0]


# ============================================
# ENDPOINTY
# ============================================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "rag-service"}


@app.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest, db: Session = Depends(get_db)):
    """
    Zwraca `top_k` najbardziej podobnych aktywnych próbek treningowych kategoryzatora.
    Podobieństwo liczone operatorem kosinusowym pgvector (`<=>`): similarity = 1 - distance.
    """
    categorizer_uuid = resolve_categorizer_uuid(db, request.categorizer_id)
    if not categorizer_uuid:
        raise HTTPException(status_code=404, detail="Categorizer not found")

    query_embedding = await embed_query(request.query_text)
    emb_literal = to_pgvector_literal(query_embedding)

    rows = db.execute(
        text(
            """
            SELECT ts.text,
                   ts.category,
                   (ts.embedding <=> CAST(:emb AS vector)) AS distance
            FROM training_samples ts
            WHERE ts.categorizer_id = CAST(:cat_id AS uuid)
              AND ts.embedding IS NOT NULL
              AND ts.is_active = TRUE
            ORDER BY distance ASC
            LIMIT :limit
            """
        ),
        {"emb": emb_literal, "cat_id": categorizer_uuid, "limit": request.top_k},
    ).fetchall()

    samples = [
        SampleItem(text=r[0], category=r[1], similarity=1.0 - float(r[2]))
        for r in rows
    ]
    return SearchResponse(
        categorizer_id=request.categorizer_id,
        query_text=request.query_text,
        samples=samples,
        count=len(samples),
    )


@app.post("/inject", response_model=InjectResponse)
async def inject_document(doc: InjectRequest, db: Session = Depends(get_db)):
    """
    Wstawia pojedynczą próbkę treningową z gotowym wektorem (pomija pipeline treningu).
    Próbka jest aktywna (is_active = TRUE) i widoczna dla wyszukiwania RAG.
    """
    if not doc.embedding:
        raise HTTPException(status_code=400, detail="Empty embedding vector")

    categorizer_uuid = resolve_categorizer_uuid(db, doc.categorizer_id)
    if not categorizer_uuid:
        raise HTTPException(status_code=404, detail="Categorizer not found")

    try:
        row = db.execute(
            text(
                """
                INSERT INTO training_samples
                    (categorizer_id, text, category, embedding, source, is_active, created_at)
                VALUES
                    (CAST(:cat_id AS uuid), :text, :category, CAST(:embedding AS vector), 'rag_inject', TRUE, NOW())
                RETURNING id
                """
            ),
            {
                "cat_id": categorizer_uuid,
                "text": doc.text,
                "category": doc.category,
                "embedding": to_pgvector_literal(doc.embedding),
            },
        ).fetchone()
        db.commit()
        return InjectResponse(status="success", inserted_id=str(row[0]))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8070)
