# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import httpx
from sqlalchemy import text
from models.database import get_db, Categorizer
from config_loader import config

router = APIRouter()

class SearchSimilarRequest(BaseModel):
    categorizer_id: str
    query_text: str
    top_k: int = 5

@router.post("/search_similar", tags=["RAG"])
async def search_similar(
    request: SearchSimilarRequest,
    db: Session = Depends(get_db)
):
    """
    RAG endpoint: Find similar training samples using pgvector similarity search
    """
    # Get categorizer
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == request.categorizer_id) |
        (Categorizer.name == request.categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    try:
        # 1. Generate embedding for query text
        async with httpx.AsyncClient(timeout=30.0) as embed_client:
            embed_response = await embed_client.post(
                f"{config.get('orchestrator.layers.embeddings.url')}/embed",
                json={"texts": [request.query_text], "normalize": True}
            )
            
            if embed_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Embedding generation failed")
            
            query_embedding = embed_response.json()["embeddings"][0]
        
        # 2. Search similar samples in DB using pgvector
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Use pgvector <=> operator for cosine distance
        query = text("""
            SELECT 
                ts.id,
                ts.text,
                ts.category,
                (ts.embedding <=> CAST(:query_emb AS vector)) as distance
            FROM training_samples ts
            WHERE ts.categorizer_id = CAST(:cat_id AS uuid)
              AND ts.embedding IS NOT NULL
            ORDER BY distance ASC
            LIMIT :limit
        """)
        
        result = db.execute(
            query,
            {
                "query_emb": embedding_str,
                "cat_id": str(categorizer.id),
                "limit": request.top_k
            }
        )
        
        similar_samples = []
        for row in result:
            similar_samples.append({
                "text": row.text,
                "category": row.category,
                "similarity": 1.0 - float(row.distance),  # Convert distance to similarity
                "distance": float(row.distance)
            })
        
        return {
            "categorizer_id": request.categorizer_id,
            "query_text": request.query_text,
            "samples": similar_samples,
            "count": len(similar_samples)
        }
        
    except Exception as e:
        import traceback
        print(f"RAG search failed: {str(e)}", flush=True)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/rag_stats/{categorizer_id}", tags=["RAG"])
async def get_rag_stats(categorizer_id: str, db: Session = Depends(get_db)):
    """Get RAG usage statistics - which samples are retrieved most"""
    # Wymaga dodania loggingu RAG queries
    # TODO: Implement RAG query logging
    
    return {
        "categorizer_id": categorizer_id,
        "message": "RAG statistics tracking not yet implemented",
        "note": "Add logging to search_similar endpoint"
    }