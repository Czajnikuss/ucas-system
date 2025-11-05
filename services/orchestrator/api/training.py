# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import re
from unidecode import unidecode
from sqlalchemy import text
from persistence import save_layer_state, load_layer_state
from models.database import SessionLocal, get_db, Categorizer, TrainingSample
from config_loader import config

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

def generate_slug(name: str) -> str:
    """Generate URL-safe slug from name"""
    slug = unidecode(name.lower())
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')

@router.post("/train", tags=["Training"])
async def train(request: TrainRequest, db: Session = Depends(get_db)):
    if not request.name or len(request.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name is required")
    
    name = request.name.strip()
    
    # Check name uniqueness
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
    
    # Generate categorizer_id from name
    categorizer_id = generate_slug(name)
    
    # Ensure categorizer_id is also unique (rare edge case)
    counter = 1
    original_slug = categorizer_id
    while db.query(Categorizer).filter(Categorizer.categorizer_id == categorizer_id).first():
        categorizer_id = f"{original_slug}-{counter}"
        counter += 1
    
    # Create new categorizer
    categorizer = Categorizer(
        categorizer_id=categorizer_id,
        name=name,
        description=request.description
    )
    db.add(categorizer)
    db.flush()
    
    # Extract categories
    categories = list(set([sample["category"] for sample in request.training_data]))
    
    # Update categorizer config
    categorizer.categories = categories
    categorizer.fallback_category = request.fallback_category
    categorizer.layers = request.layers
    categorizer.config = {
        "tags_config": request.tags_config,
        "xgboost_config": request.xgboost_config,
        "llm_config": request.llm_config,
        "hil_config": request.hil_config
    }
    
    # Save training samples
    training_samples_list = []
    for sample in request.training_data:
        training_sample = TrainingSample(
            categorizer_id=categorizer.id,
            text=sample["text"],
            category=sample["category"]
        )
        db.add(training_sample)
        training_samples_list.append(training_sample)
    
    # Flush to generate IDs
    db.flush()
    
    # Generate embeddings for all training samples
    embedding_success = False
    if training_samples_list:
        texts = [s.text for s in training_samples_list]
        import sys
        print("=" * 60, file=sys.stderr, flush=True)
        print(f"EMBEDDING GENERATION START", file=sys.stderr, flush=True)
        print(f"Samples to process: {len(training_samples_list)}", file=sys.stderr, flush=True)
        print(f"First sample ID: {training_samples_list[0].id}", file=sys.stderr, flush=True)
        print(f"Texts to embed: {texts[:2]}..." if len(texts) > 2 else f"Texts: {texts}", file=sys.stderr, flush=True)
        
        try:
            print("Creating HTTP client...", file=sys.stderr, flush=True)
            async with httpx.AsyncClient(timeout=30.0) as embed_client:
                print(f"Making POST to {config.get('orchestrator.layers.embeddings.url')}/embed", file=sys.stderr, flush=True)
                
                embed_response = await embed_client.post(
                    f"{config.get('orchestrator.layers.embeddings.url')}/embed",
                    json={"texts": texts, "normalize": True}
                )
                
                print(f"Response status: {embed_response.status_code}", file=sys.stderr, flush=True)
                
                if embed_response.status_code == 200:
                    embed_data = embed_response.json()
                    embeddings = embed_data["embeddings"]
                    print(f"Received {len(embeddings)} embeddings, {len(embeddings[0])} dims", file=sys.stderr, flush=True)
                    
                    # Store embeddings in DB
                    for i, training_sample in enumerate(training_samples_list):
                        if i < len(embeddings):
                            embedding_str = "[" + ",".join(map(str, embeddings[i])) + "]"
                            print(f"Storing embedding for sample {training_sample.id} (length: {len(embedding_str)})", file=sys.stderr, flush=True)
                            db.execute(
                                text("UPDATE training_samples SET embedding = CAST(:emb AS vector) WHERE id = CAST(:id AS uuid)"),
                                {"emb": embedding_str, "id": str(training_sample.id)}
                            )

                    
                    embedding_success = True
                    print(f"✓ All embeddings stored successfully", file=sys.stderr, flush=True)
                else:
                    print(f"✗ HTTP error: {embed_response.status_code} - {embed_response.text[:200]}", file=sys.stderr, flush=True)
                    
        except httpx.ConnectError as e:
            print(f"✗ CONNECTION ERROR: Cannot reach embeddings service: {e}", file=sys.stderr, flush=True)
        except httpx.TimeoutException as e:
            print(f"✗ TIMEOUT ERROR: Embeddings service timeout: {e}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"✗ UNEXPECTED ERROR: {type(e).__name__}: {str(e)}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
        
        print(f"EMBEDDING GENERATION END (success={embedding_success})", file=sys.stderr, flush=True)
        print("=" * 60, file=sys.stderr, flush=True)
    
    db.commit()

    
        # Train layers and save state
    results = {}
    async with httpx.AsyncClient() as client:
        if "tags" in request.layers:
            tags_request = {
                "categorizer_id": categorizer_id,
                "training_data": request.training_data,
                **(request.tags_config or {})
            }
            try:
                response = await client.post(f"{config.get('orchestrator.layers.tags.url')}/train", json=tags_request, timeout=30.0)
                result = response.json()
                results["tags"] = result
                
                # Save FULL tags state to disk
                if result.get("status") == "trained":
                    tags_state = {
                        "keywords": result.get("keywords", {}),
                        "categories": result.get("categories", []),
                        "patterns": result.get("patterns", {})
                    }
                    save_layer_state(categorizer_id, "tags", tags_state)
            except Exception as e:
                results["tags"] = {"error": str(e)}
        
        if "xgboost" in request.layers:
            xgb_request = {
                "categorizer_id": categorizer_id,
                "training_data": request.training_data,
                **(request.xgboost_config or {})
            }
            try:
                response = await client.post(f"{config.get('orchestrator.layers.xgboost.url')}/train", json=xgb_request, timeout=60.0)
                result = response.json()
                results["xgboost"] = result
                
                # XGBoost model serialization needs special handling
                # TODO: Implement after we add model export endpoint to XGBoost layer
                
            except Exception as e:
                results["xgboost"] = {"error": str(e)}
        
        if "llm" in request.layers:
            llm_request = {
                "categorizer_id": categorizer_id,
                "training_data": request.training_data,
                "model": "phi3:mini",
                "fallback_category": request.fallback_category,
                **(request.llm_config or {})
            }
            try:
                response = await client.post(f"{config.get('orchestrator.layers.llm.url')}/train", json=llm_request, timeout=60.0)
                result = response.json()
                results["llm"] = result
                
                # Save LLM config to disk
                llm_config = {
                    "categories": result.get("categories", []),
                    "fallback_category": result.get("fallback_category"),
                    "training_samples": request.training_data,
                    "model": result.get("model", "phi3:mini")
                }
                save_layer_state(categorizer_id, "llm", llm_config)
                
            except Exception as e:
                results["llm"] = {"error": str(e)}

    
    return {
        "status": "trained",
        "categorizer_id": categorizer_id,
        "name": name,
        "categories": categories,
        "fallback_category": request.fallback_category,
        "training_samples": len(request.training_data),
        "embeddings_generated": embedding_success,
        "layers": request.layers,
        "results": results
    }