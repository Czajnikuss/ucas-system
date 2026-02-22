# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import os

app = FastAPI(title="UCAS RAG Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DocumentInject(BaseModel):
    categorizer_id: str
    text: str
    category: str
    embedding: List[float]

class DocumentInjectResponse(BaseModel):
    status: str
    inserted_id: str

class SearchRequest(BaseModel):
    categorizer_id: str
    embedding: List[float]
    limit: int = 5

class SearchResultItem(BaseModel):
    text: str
    category: str
    similarity: float

class SearchResponse(BaseModel):
    results: List[SearchResultItem]

@app.post("/inject", response_model=DocumentInjectResponse)
async def inject_document(doc: DocumentInject, db: Session = Depends(get_db)):
    if len(doc.embedding) == 0:
        raise HTTPException(status_code=400, detail="Empty embedding vector")

    try:
        query = text("""
            INSERT INTO training_samples (categorizer_id_str, text, category, embedding, created_at)
            VALUES (:cat_id, :text, :category, :embedding, NOW())
            RETURNING id
        """)
        
        result = db.execute(query, {
            "cat_id": doc.categorizer_id,
            "text": doc.text,
            "category": doc.category,
            "embedding": str(doc.embedding) 
        })
        inserted_id = str(result.fetchone()[0])
        db.commit()
        
        return DocumentInjectResponse(status="success", inserted_id=inserted_id)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest, db: Session = Depends(get_db)):
    if not request.embedding:
        raise HTTPException(status_code=400, detail="Empty embedding vector")

    try:
        # Operator <=> w pgvector oblicza odległość kosinusową.
        # 1 - (embedding <=> wektor) daje nam klasyczne cosine similarity.
        query = text("""
            SELECT text, category, 1 - (embedding <=> :embedding) AS similarity
            FROM training_samples
            WHERE categorizer_id_str = :cat_id
            ORDER BY embedding <=> :embedding
            LIMIT :limit
        """)
        
        result = db.execute(query, {
            "cat_id": request.categorizer_id,
            "embedding": str(request.embedding),
            "limit": request.limit
        })
        
        docs = [
            SearchResultItem(text=row[0], category=row[1], similarity=float(row[2]))
            for row in result.fetchall()
        ]
        return SearchResponse(results=docs)
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))