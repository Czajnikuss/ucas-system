# services/rag-service/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import time

app = FastAPI(
    title="UCAS RAG Service",
    version="1.0.0",
    description="Retrieval-Augmented Generation using pgvector",
    docs_url="/swagger"
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db"
)

EMBEDDINGS_URL = os.getenv(
    "EMBEDDINGS_SERVICE_URL",
    "http://embeddings-service:8050"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# === Models ===

class SearchRequest(BaseModel):
    categorizer_id: str
    query_text: str
    top_k: int = 5
    similarity_threshold: float = 0.7
    include_inactive: bool = False

class SearchResult(BaseModel):
    sample_id: str
    text: str
    category: str
    similarity: float
    distance: float
    quality_score: Optional[float] = None

class SearchResponse(BaseModel):
    categorizer_id: str
    query_text: str
    count: int
    samples: List[SearchResult]
    processing_time_ms: float
    embedding_time_ms: float
    search_time_ms: float

# === Endpoints ===

@app.get("/")
async def root():
    return {
        "service": "UCAS RAG Service",
        "status": "running",
        "version": "1.0.0",
        "features": ["vector_search", "query_logging", "pgvector"]
    }

@app.get("/health")
async def health():
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{EMBEDDINGS_URL}/health")
            emb_status = "connected" if resp.status_code == 200 else "error"
    except:
        emb_status = "unreachable"
    
    return {
        "status": "healthy",
        "database": db_status,
        "embeddings_service": emb_status
    }

@app.post("/search", response_model=SearchResponse)
async def search_similar(request: SearchRequest):
    """
    Vector similarity search in pgvector
    
    1. Generate embedding via embeddings-service
    2. Search in pgvector using cosine distance
    3. Return top-k results
    """
    start_time = time.time()
    
    db = SessionLocal()
    
    try:
        # 1. Get categorizer UUID
        cat_query = text("""
            SELECT id FROM categorizers 
            WHERE categorizer_id = :cat_id OR name = :cat_id
        """)
        
        cat_result = db.execute(cat_query, {"cat_id": request.categorizer_id}).first()
        
        if not cat_result:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        categorizer_uuid = str(cat_result[0])
        
        # 2. Generate embedding
        embed_start = time.time()
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            embed_resp = await client.post(
                f"{EMBEDDINGS_URL}/embed",
                json={"texts": [request.query_text], "normalize": True}
            )
            
            if embed_resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=f"Embedding generation failed: {embed_resp.text}"
                )
            
            query_embedding = embed_resp.json()["embeddings"][0]
        
        embedding_time = (time.time() - embed_start) * 1000
        
        # 3. Vector search in pgvector
        search_start = time.time()
        
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        active_filter = "AND ts.is_active = TRUE" if not request.include_inactive else ""
        
        search_query = text(f"""
            SELECT 
                ts.id,
                ts.text,
                ts.category,
                ts.quality_score,
                (ts.embedding <=> CAST(:query_emb AS vector)) as distance
            FROM training_samples ts
            WHERE ts.categorizer_id = CAST(:cat_id AS uuid)
              AND ts.embedding IS NOT NULL
              {active_filter}
              AND (1 - (ts.embedding <=> CAST(:query_emb AS vector))) >= :threshold
            ORDER BY ts.embedding <=> CAST(:query_emb AS vector)
            LIMIT :limit
        """)
        
        result = db.execute(
            search_query,
            {
                "query_emb": embedding_str,
                "cat_id": categorizer_uuid,
                "threshold": request.similarity_threshold,
                "limit": request.top_k
            }
        )
        
        samples = []
        for row in result:
            samples.append(SearchResult(
                sample_id=str(row.id),
                text=row.text,
                category=row.category,
                distance=float(row.distance),
                similarity=1.0 - float(row.distance),
                quality_score=float(row.quality_score) if row.quality_score else None
            ))
        
        search_time = (time.time() - search_start) * 1000
        total_time = (time.time() - start_time) * 1000
        
        return SearchResponse(
            categorizer_id=request.categorizer_id,
            query_text=request.query_text,
            count=len(samples),
            samples=samples,
            processing_time_ms=total_time,
            embedding_time_ms=embedding_time,
            search_time_ms=search_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )
    finally:
        db.close()

@app.get("/stats/{categorizer_id}")
async def get_stats(categorizer_id: str):
    """Get RAG usage statistics (placeholder for now)"""
    # TODO: Implement query logging
    return {
        "categorizer_id": categorizer_id,
        "message": "Statistics tracking coming soon",
        "features": ["query_count", "popular_samples", "avg_similarity"]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8070)