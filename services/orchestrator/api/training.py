# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Tuple
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


async def _generate_embeddings(samples: List[TrainingSample]) -> Tuple[List, bool]:
    """Generuje embeddingi (batch po 100 — limit embeddings-service) dla listy TrainingSample
    i przypisuje je do .embedding. Zwraca (lista_embeddingow, sukces)."""
    if not samples:
        return [], False
    texts = [s.text for s in samples]
    chunk_size = 100
    all_embeddings: List = []
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for start in range(0, len(texts), chunk_size):
                chunk = texts[start:start + chunk_size]
                resp = await client.post(
                    f"{config.get('orchestrator.layers.embeddings.url')}/embed",
                    json={"texts": chunk, "normalize": True},
                )
                if resp.status_code == 200:
                    all_embeddings.extend(resp.json().get("embeddings", []))
                else:
                    print(f"🔴 Embeddings error: {resp.status_code}", file=sys.stderr, flush=True)
                    return [], False
        if len(all_embeddings) == len(samples):
            for s, emb in zip(samples, all_embeddings):
                s.embedding = emb
            return all_embeddings, True
    except Exception as e:
        print(f"🔴 Błąd przy generowaniu embeddingów: {e}", file=sys.stderr, flush=True)
    return [], False


async def _train_all_layers(categorizer_id: str, training_data: List[Dict[str, str]], layers: List[str],
                            tags_config: Optional[Dict], xgboost_config: Optional[Dict],
                            llm_config: Optional[Dict], fallback_category: Optional[str],
                            all_embeddings: List, embedding_success: bool) -> Dict:
    """Trenuje skonfigurowane warstwy (tags/xgboost/llm) na podanych danych. Wspolny rdzen
    dla /train i /retrain. xgboost dostaje pretrenowane embeddingi (transfer learning) gdy dostepne."""
    results: Dict = {}
    async with httpx.AsyncClient() as client:
        if "tags" in layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.tags.url')}/train",
                    json={"categorizer_id": categorizer_id, "training_data": training_data, **(tags_config or {})},
                    timeout=30.0,
                )
                results["tags"] = response.json()
                if results["tags"].get("status") == "trained":
                    save_layer_state(categorizer_id, "tags", {
                        "keywords": results["tags"].get("keywords", {}),
                        "categories": results["tags"].get("categories", []),
                    })
            except Exception as e:
                results["tags"] = {"error": str(e)}

        if "xgboost" in layers:
            try:
                xgb_payload = {"categorizer_id": categorizer_id, "training_data": training_data, **(xgboost_config or {})}
                if embedding_success and len(all_embeddings) == len(training_data):
                    xgb_payload["embeddings"] = all_embeddings
                response = await client.post(
                    f"{config.get('orchestrator.layers.xgboost.url')}/train",
                    json=xgb_payload,
                    timeout=120.0,
                )
                results["xgboost"] = response.json()
            except Exception as e:
                results["xgboost"] = {"error": str(e)}

        if "llm" in layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.llm.url')}/train",
                    json={"categorizer_id": categorizer_id, "training_data": training_data,
                          "model": config.get('orchestrator.layers.llm.model', 'phi3:mini'),
                          "fallback_category": fallback_category, **(llm_config or {})},
                    timeout=60.0,
                )
                results["llm"] = response.json()
                if results["llm"].get("status") == "trained":
                    save_layer_state(categorizer_id, "llm", {
                        "categories": results["llm"].get("categories", []),
                        "fallback_category": results["llm"].get("fallback_category"),
                        "training_samples": training_data,
                        "model": results["llm"].get("model", "phi3:mini"),
                    })
            except Exception as e:
                results["llm"] = {"error": str(e)}
    return results


@router.post("/train", tags=["Training"], response_model=TrainResponse)
async def train(request: TrainRequest, db: Session = Depends(get_db)):
    if not request.name or len(request.name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name is required")

    name = request.name.strip()

    existing = db.query(Categorizer).filter(Categorizer.name == name).first()
    if existing:
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
                "suggestions": [f"{name} 2", f"{name} V2", f"{name} {datetime.now().strftime('%b%Y')}"]
            }
        )

    categorizer_id = generate_slug(name)
    counter = 1
    original_slug = categorizer_id
    while db.query(Categorizer).filter(Categorizer.categorizer_id == categorizer_id).first():
        categorizer_id = f"{original_slug}-{counter}"
        counter += 1

    categorizer = Categorizer(categorizer_id=categorizer_id, name=name, description=request.description)
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
        "hil_config": request.hil_config,
    }

    training_samples_list = []
    for sample in request.training_data:
        ts = TrainingSample(categorizer_id=categorizer.id, text=sample["text"], category=sample["category"])
        db.add(ts)
        training_samples_list.append(ts)
    db.flush()

    all_embeddings, embedding_success = await _generate_embeddings(training_samples_list)
    db.commit()

    results = await _train_all_layers(
        categorizer_id, request.training_data, request.layers,
        request.tags_config, request.xgboost_config, request.llm_config,
        request.fallback_category, all_embeddings, embedding_success,
    )

    return TrainResponse(
        status="trained",
        categorizer_id=categorizer_id,
        name=name,
        categories=categories,
        fallback_category=request.fallback_category,
        training_samples=len(request.training_data),
        embeddings_generated=embedding_success,
        layers=request.layers,
        results=results,
    )


@router.post("/categorizers/{categorizer_id}/retrain", tags=["Training"])
async def retrain(categorizer_id: str, db: Session = Depends(get_db)):
    """
    Retrening z AKTYWNYCH próbek DB (bez tworzenia nowego kategoryzatora, bez konfliktu 409).
    Domyka pętlę samodoskonalenia: po korektach HIL i kuracji modele (tags/xgboost/llm)
    są uczone na aktualnym, wykurowanym zbiorze. Konfiguracja warstw brana z kategoryzatora.
    """
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) | (Categorizer.name == categorizer_id)
    ).first()
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")

    active = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer.id,
        TrainingSample.is_active == True
    ).all()
    if len(active) < 2:
        raise HTTPException(status_code=400, detail="Za malo aktywnych probek do treningu")

    training_data = [{"text": s.text, "category": s.category} for s in active]
    categories = list(set(s.category for s in active))
    categorizer.categories = categories
    categorizer.updated_at = datetime.utcnow()

    all_embeddings, embedding_success = await _generate_embeddings(active)
    db.commit()

    cfg = categorizer.config or {}
    results = await _train_all_layers(
        categorizer.categorizer_id, training_data, categorizer.layers or ["tags", "xgboost", "llm"],
        cfg.get("tags_config"), cfg.get("xgboost_config"), cfg.get("llm_config"),
        categorizer.fallback_category, all_embeddings, embedding_success,
    )

    return {
        "status": "retrained",
        "categorizer_id": categorizer.categorizer_id,
        "training_samples": len(training_data),
        "categories": categories,
        "embeddings_generated": embedding_success,
        "results": results,
    }
