# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import re
from unidecode import unidecode
from persistence import save_layer_state
from models.database import get_db, Categorizer, TrainingSample
from config_loader import config
import sys

router = APIRouter()

class TrainRequest(BaseModel):
    name: str
    description: Optional[str] = None
    training_data: List[Dict[str, str]]
    layers: Optional[List[str]] = ["tags", "xgboost", "llm"]
    tags_config: Optional[Dict] = None
    xgboost_config: Optional[Dict] = None
    llm_config: Optional[Dict] = None
    hil_config: Optional[Dict] = {
        "enabled": True,
        "tags_threshold": 0.7,
        "xgboost_threshold": 0.7,
        "llm_threshold": 0.8
    }
    fallback_category: Optional[str] = None

class TrainResponse(BaseModel):
    status: str
    categorizer_id: str
    name: str
    categories: List[str]
    fallback_category: Optional[str]
    training_samples: int
    embeddings_generated: bool
    layers: List[str]
    results: Dict

def generate_slug(name: str) -> str:
    """Generate URL-safe slug from name"""
    slug = unidecode(name.lower())
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')

@router.post("/train", tags=["Training"], response_model=TrainResponse)
async def train(request: TrainRequest, db: Session = Depends(get_db)):
    if not request.name or len(request.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name is required")
    
    name = request.name.strip()
    
    existing = db.query(Categorizer).filter(Categorizer.name == name).first()
    
    if existing:
        suggestions = [
            f"{name} 2",
            f"{name} V2",
            f"{name} {datetime.now().strftime('%b%Y')}"
        ]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "Name already exists",
                "conflicting_name": name,
                "existing_categorizer": {
                    "id": str(existing.id),
                    "categorizer_id": existing.categorizer_id,
                    "created_at": existing.created_at.isoformat()
                },
                "suggestions": suggestions
            }
        )
    
    categorizer_id = generate_slug(name)
    counter = 1
    original_slug = categorizer_id
    while db.query(Categorizer).filter(Categorizer.categorizer_id == categorizer_id).first():
        categorizer_id = f"{original_slug}-{counter}"
        counter += 1
    
    categorizer = Categorizer(
        categorizer_id=categorizer_id,
        name=name,
        description=request.description
    )
    db.add(categorizer)
    db.flush()
    
    categories = list(set([sample["category"] for sample in request.training_data]))
    
    categorizer.categories = categories
    categorizer.fallback_category = request.fallback_category
    categorizer.layers = request.layers
    categorizer.config = {
        "tags_config": request.tags_config,
        "xgboost_config": request.xgboost_config,
        "llm_config": request.llm_config,
        "hil_config": request.hil_config
    }
    
    training_samples_list = []
    for sample in request.training_data:
        training_sample = TrainingSample(
            categorizer_id=categorizer.id,
            text=sample["text"],
            category=sample["category"]
        )
        db.add(training_sample)
        training_samples_list.append(training_sample)
    
    db.flush()
    
    embedding_success = False
    if training_samples_list:
        texts = [s.text for s in training_samples_list]
        # embeddings-service ma limit 100 tekstow na request -> batchujemy po 100,
        # inaczej dla wiekszych zbiorow dostajemy 400 i embeddingi sie nie zapisuja.
        chunk_size = 100
        all_embeddings = []
        try:
            async with httpx.AsyncClient(timeout=60.0) as embed_client:
                for start in range(0, len(texts), chunk_size):
                    chunk = texts[start:start + chunk_size]
                    embed_response = await embed_client.post(
                        f"{config.get('orchestrator.layers.embeddings.url')}/embed",
                        json={"texts": chunk, "normalize": True}
                    )
                    if embed_response.status_code == 200:
                        all_embeddings.extend(embed_response.json().get("embeddings", []))
                    else:
                        print(f"🔴 Embeddings error: {embed_response.status_code}", file=sys.stderr, flush=True)
                        all_embeddings = []
                        break

            if len(all_embeddings) == len(training_samples_list):
                # 🎯 N+1 eliminacja: przypisanie obiektowe (pgvector obsługuje natywne listy)
                for training_sample, emb in zip(training_samples_list, all_embeddings):
                    training_sample.embedding = emb
                embedding_success = True
        except Exception as e:
            print(f"🔴 Błąd przy generowaniu embeddingów: {e}", file=sys.stderr, flush=True)
    
    db.commit()

    results = {}
    async with httpx.AsyncClient() as client:
        if "tags" in request.layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.tags.url')}/train", 
                    json={"categorizer_id": categorizer_id, "training_data": request.training_data, **(request.tags_config or {})}, 
                    timeout=30.0
                )
                results["tags"] = response.json()
                if results["tags"].get("status") == "trained":
                    save_layer_state(categorizer_id, "tags", {
                        "keywords": results["tags"].get("keywords", {}),
                        "categories": results["tags"].get("categories", [])
                    })
            except Exception as e:
                results["tags"] = {"error": str(e)}
        
        if "xgboost" in request.layers:
            try:
                xgb_payload = {"categorizer_id": categorizer_id, "training_data": request.training_data, **(request.xgboost_config or {})}
                # Transfer learning: jesli udalo sie policzyc pretrenowane embeddingi, podajemy je
                # jako cechy (wyrownane do training_data). Inaczej xgboost-layer uzyje Word2Vec.
                if embedding_success and len(all_embeddings) == len(request.training_data):
                    xgb_payload["embeddings"] = all_embeddings
                response = await client.post(
                    f"{config.get('orchestrator.layers.xgboost.url')}/train",
                    json=xgb_payload,
                    timeout=120.0
                )
                results["xgboost"] = response.json()
            except Exception as e:
                results["xgboost"] = {"error": str(e)}
        
        if "llm" in request.layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.llm.url')}/train", 
                    json={"categorizer_id": categorizer_id, "training_data": request.training_data, "model": "phi3:mini", "fallback_category": request.fallback_category, **(request.llm_config or {})}, 
                    timeout=60.0
                )
                results["llm"] = response.json()
                if results["llm"].get("status") == "trained":
                    save_layer_state(categorizer_id, "llm", {
                        "categories": results["llm"].get("categories", []),
                        "fallback_category": results["llm"].get("fallback_category"),
                        "training_samples": request.training_data,
                        "model": results["llm"].get("model", "phi3:mini")
                    })
            except Exception as e:
                results["llm"] = {"error": str(e)}

    return TrainResponse(
        status="trained",
        categorizer_id=categorizer_id,
        name=name,
        categories=categories,
        fallback_category=request.fallback_category,
        training_samples=len(request.training_data),
        embeddings_generated=embedding_success,
        layers=request.layers,
        results=results
    )