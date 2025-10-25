# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import numpy as np
import time

app = FastAPI(
    title="UCAS Embeddings Service",
    version="1.0.0",
    description="Generate semantic embeddings for text using multilingual models",
    docs_url="/swagger"
)

# Load model at startup (singleton)
model = None
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
MODEL_DIMENSIONS = 384

@app.on_event("startup")
async def load_model():
    global model
    print(f"Loading embedding model: {MODEL_NAME}...")
    start = time.time()
    model = SentenceTransformer(MODEL_NAME)
    print(f"Model loaded in {time.time() - start:.2f}s")


class EmbedRequest(BaseModel):
    texts: List[str]
    normalize: Optional[bool] = True


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dimensions: int
    count: int
    processing_time_ms: float


class SimilarityRequest(BaseModel):
    text1: str
    text2: str


class SimilarityResponse(BaseModel):
    similarity: float
    text1: str
    text2: str


@app.get("/")
async def root():
    return {
        "service": "UCAS Embeddings Service",
        "status": "running",
        "model": MODEL_NAME,
        "dimensions": MODEL_DIMENSIONS,
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    return {
        "status": "healthy",
        "model": MODEL_NAME,
        "dimensions": MODEL_DIMENSIONS,
        "model_loaded": model is not None
    }


@app.post("/embed", response_model=EmbedResponse)
async def generate_embeddings(request: EmbedRequest):
    """Generate embeddings for a list of texts"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    if not request.texts:
        raise HTTPException(status_code=400, detail="No texts provided")
    
    if len(request.texts) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 texts per request")
    
    try:
        start = time.time()
        
        # Generate embeddings
        embeddings = model.encode(
            request.texts,
            normalize_embeddings=request.normalize,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        processing_time = (time.time() - start) * 1000
        
        # Convert to list for JSON serialization
        embeddings_list = embeddings.tolist()
        
        return EmbedResponse(
            embeddings=embeddings_list,
            model=MODEL_NAME,
            dimensions=MODEL_DIMENSIONS,
            count=len(request.texts),
            processing_time_ms=processing_time
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")


@app.post("/similarity", response_model=SimilarityResponse)
async def compute_similarity(request: SimilarityRequest):
    """Compute cosine similarity between two texts"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        # Generate embeddings
        embeddings = model.encode(
            [request.text1, request.text2],
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True
        )
        
        # Compute cosine similarity (dot product of normalized vectors)
        similarity = float(np.dot(embeddings[0], embeddings[1]))
        
        return SimilarityResponse(
            similarity=similarity,
            text1=request.text1,
            text2=request.text2
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Similarity computation failed: {str(e)}")


@app.get("/model/info")
async def get_model_info():
    """Get information about the loaded model"""
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    return {
        "model_name": MODEL_NAME,
        "dimensions": MODEL_DIMENSIONS,
        "max_seq_length": model.max_seq_length,
        "tokenizer": model.tokenizer.__class__.__name__,
        "device": str(model.device)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8050)
