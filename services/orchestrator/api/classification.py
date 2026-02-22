# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import asyncio
from models.database import get_db, Categorizer, Classification
from config_loader import config

router = APIRouter()

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str
    strategy: str = "cascade"
    save_to_history: bool = True
    context: Optional[Dict] = None
    return_prompt: bool = False  # 🎯 Domyślnie wyłączone dla oszczędności sieci

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    method: str
    reasoning: Optional[str] = None
    processing_time_ms: float
    is_fallback: bool = False
    cascade_results: Optional[Dict[str, Any]] = None
    layer_results: Optional[Dict[str, Any]] = None
    prompt: Optional[str] = None

@router.post("/classify", tags=["Classification"], response_model=ClassifyResponse)
async def classify(request: ClassifyRequest, db: Session = Depends(get_db)):
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == request.categorizer_id) |
        (Categorizer.name == request.categorizer_id)
    ).one_or_none()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail=f"Categorizer not found")

    start_time = datetime.now()
    valid_strategies = ["cascade", "all", "fastest", "tags", "xgboost", "llm"]
    if request.strategy not in valid_strategies:
        raise HTTPException(status_code=400, detail=f"Invalid strategy: {request.strategy}")
    
    if request.strategy == "cascade":
        result = await classify_cascade(request.categorizer_id, request.text, db, request.context)
    elif request.strategy == "all":
        result = await classify_all(request.categorizer_id, request.text)
    elif request.strategy == "fastest":
        result = await classify_fastest(request.categorizer_id, request.text)
    elif request.strategy in ["tags", "xgboost", "llm"]:
        result = await classify_single_layer(request.categorizer_id, request.text, request.strategy, request.context)
    
    processing_time = (datetime.now() - start_time).total_seconds() * 1000
    result["processing_time_ms"] = processing_time
    
    # Przechwytujemy surowy prompt z wewnętrznego JSONa, jeśli warstwa LLM go zwróciła
    extracted_prompt = None
    if "cascade_results" in result and "llm" in result["cascade_results"]:
        extracted_prompt = result["cascade_results"]["llm"].get("prompt_used")
        # Usuwamy prompt z kaskady, żeby nie śmiecić głównego wyjścia
        if not request.return_prompt and "prompt_used" in result["cascade_results"]["llm"]:
            del result["cascade_results"]["llm"]["prompt_used"]
            
    if "cascade_results" in result:
        result["layer_results"] = result["cascade_results"]
        
    if request.return_prompt and extracted_prompt:
        result["prompt"] = extracted_prompt
    
    if request.save_to_history:
        classification = Classification(
            categorizer_id=categorizer.id,
            text=request.text,
            predicted_category=result.get("category"),
            confidence=result.get("confidence"),
            method=result.get("method"),
            is_fallback=result.get("is_fallback", False),
            processing_time_ms=processing_time,
            cascade_results=result.get("cascade_results"),
            llm_prompt=extracted_prompt  # 🎯 Zapis do PostgreSQL
        )
        db.add(classification)
        db.commit()
    
    return ClassifyResponse(**result)

# ... (reszta funkcji classify_single_layer, classify_cascade, classify_all, classify_fastest pozostaje BEZ ZMIAN z poprzedniej działającej iteracji)

async def classify_single_layer(categorizer_id: str, text: str, layer: str, context: Optional[Dict] = None) -> Dict:
    """Omija kaskadę i uderza do konkretnej warstwy"""
    async with httpx.AsyncClient() as client:
        try:
            payload = {"categorizer_id": categorizer_id, "text": text}
            if layer == "llm" and context:
                payload["context"] = context
                
            response = await client.post(
                f"{config.get(f'orchestrator.layers.{layer}.url')}/classify",
                json=payload,
                timeout=60.0
            )
            result = response.json()
            return {
                "category": result.get("category"),
                "confidence": result.get("confidence", 0.0),
                "method": layer,
                "reasoning": result.get("reasoning", f"Direct {layer} hit"),
                "cascade_results": {layer: result},
                "is_fallback": result.get("is_fallback", False)
            }
        except Exception as e:
            return {
                "category": None,
                "confidence": 0.0,
                "method": "error",
                "reasoning": str(e),
                "cascade_results": {layer: {"error": str(e)}},
                "is_fallback": False
            }

async def classify_cascade(categorizer_id: str, text: str, db: Session, context: Optional[Dict] = None) -> Dict:
    """Cascade strategy: Tags -> XGBoost -> LLM -> HIL (skip layers not in config)"""
    cascade_results = {}
    
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    if not categorizer:
        return {"category": None, "confidence": 0.0, "method": "error", "reasoning": "Categorizer not found", "cascade_results": {}, "is_fallback": False}
    
    configured_layers = categorizer.layers or []
    cat_config = categorizer.config or {}
    hil_config = cat_config.get('hil_config') or {}
    
    tags_threshold = hil_config.get('tags_threshold', 0.7)
    xgboost_threshold = hil_config.get('xgboost_threshold', 0.7)
    llm_threshold = hil_config.get('llm_threshold', 0.8)
    
    hil_enabled_in_layers = "hil" in configured_layers
    hil_enabled_in_config = hil_config.get('enabled', True)
    should_check_hil = hil_enabled_in_layers and hil_enabled_in_config
    
    async with httpx.AsyncClient() as client:
        # Layer 1: Tags
        if "tags" in configured_layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.tags.url')}/classify",
                    json={"categorizer_id": categorizer_id, "text": text},
                    timeout=5.0
                )
                response.raise_for_status() # 🎯 Krytyczne
                tags_result = response.json()
                cascade_results["tags"] = tags_result
                
                if tags_result.get("confidence", 0) >= tags_threshold and tags_result.get("category"):
                    return {"category": tags_result["category"], "confidence": tags_result["confidence"], "method": "tags", "reasoning": "Exact keyword match", "cascade_results": cascade_results, "is_fallback": False}
            except Exception as e:
                cascade_results["tags"] = {"error": str(e)}
        
        # Layer 2: XGBoost
        if "xgboost" in configured_layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.xgboost.url')}/classify",
                    json={"categorizer_id": categorizer_id, "text": text},
                    timeout=10.0
                )
                response.raise_for_status() # 🎯 Krytyczne
                xgb_result = response.json()
                cascade_results["xgboost"] = xgb_result
                
                if xgb_result.get("confidence", 0) >= xgboost_threshold and xgb_result.get("category"):
                    return {"category": xgb_result["category"], "confidence": xgb_result["confidence"], "method": "xgboost", "reasoning": "High confidence ML prediction", "cascade_results": cascade_results, "is_fallback": False}
            except Exception as e:
                cascade_results["xgboost"] = {"error": str(e)}
        
        # Layer 3: LLM
        if "llm" in configured_layers:
            try:
                payload = {"categorizer_id": categorizer_id, "text": text}
                if context:
                    payload["context"] = context
                    
                response = await client.post(
                    f"{config.get('orchestrator.layers.llm.url')}/classify",
                    json=payload,
                    timeout=60.0
                )
                response.raise_for_status() # 🎯 Krytyczne (zabije ślepe parsowanie 422 JSON)
                llm_result = response.json()
                cascade_results["llm"] = llm_result
                
                llm_confidence = llm_result.get("confidence", 0.0)
                
                tags_conf = cascade_results.get("tags", {}).get("confidence", 0)
                xgb_conf = cascade_results.get("xgboost", {}).get("confidence", 0)
                
                escalate = should_check_hil and all([
                    tags_conf < tags_threshold,
                    xgb_conf < xgboost_threshold,
                    llm_confidence < llm_threshold
                ])
                
                if escalate:
                    try:
                        hil_response = await client.post(
                            f"{config.get('orchestrator.layers.hil.url')}/escalate",
                            json={
                                "categorizer_id": categorizer_id,
                                "text": text,
                                "suggested_category": llm_result.get("category"),
                                "suggested_confidence": llm_confidence,
                                "context": cascade_results
                            },
                            timeout=5.0
                        )
                        hil_response.raise_for_status()
                        hil_result = hil_response.json()
                        cascade_results["hil"] = hil_result
                        
                        return {"category": None, "confidence": 0.0, "method": "hil_pending", "reasoning": f"Escalated to HIL (Review ID: {hil_result.get('review_id')})", "cascade_results": cascade_results, "is_fallback": False, "hil_review_id": hil_result.get("review_id")}
                    except Exception as e:
                        cascade_results["hil"] = {"error": str(e)}
                
                return {"category": llm_result.get("category"), "confidence": llm_confidence, "method": "llm", "reasoning": llm_result.get("reasoning", ""), "cascade_results": cascade_results, "is_fallback": llm_result.get("is_fallback", False)}
            except Exception as e:
                cascade_results["llm"] = {"error": str(e)}
        
        # Fallback handling
        if categorizer.fallback_category:
            return {"category": categorizer.fallback_category, "confidence": 0.0, "method": "fallback", "reasoning": "Used fallback category due to low confidence across all layers", "cascade_results": cascade_results, "is_fallback": True}

        return {"category": None, "confidence": 0.0, "method": "error", "reasoning": "All configured layers failed or returned low confidence", "cascade_results": cascade_results, "is_fallback": False}

async def classify_all(categorizer_id: str, text: str) -> Dict:
    async with httpx.AsyncClient() as client:
        tasks = [
            client.post(f"{config.get('orchestrator.layers.tags.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=5.0),
            client.post(f"{config.get('orchestrator.layers.xgboost.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=10.0),
            client.post(f"{config.get('orchestrator.layers.llm.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=60.0)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_results = {}
        best_result = None
        best_confidence = 0.0
        
        for result, layer in zip(results, ["tags", "xgboost", "llm"]):
            if isinstance(result, Exception):
                all_results[layer] = {"error": str(result)}
            else:
                data = result.json()
                all_results[layer] = data
                if data.get("confidence", 0) > best_confidence and data.get("category"):
                    best_confidence = data["confidence"]
                    best_result = {
                        "category": data["category"],
                        "confidence": data["confidence"],
                        "method": layer,
                        "reasoning": data.get("reasoning", f"Best from {layer}"),
                        "is_fallback": data.get("is_fallback", False)
                    }
        
        if best_result:
            best_result["cascade_results"] = all_results
            return best_result
        
        return {"category": None, "confidence": 0.0, "method": "error", "cascade_results": all_results, "is_fallback": False}

async def classify_fastest(categorizer_id: str, text: str) -> Dict:
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{config.get('orchestrator.layers.tags.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=2.0)
            result = response.json()
            if result.get("category"):
                return {"category": result["category"], "confidence": result["confidence"], "method": "tags", "is_fallback": False}
        except: pass
        return {"category": None, "confidence": 0.0, "method": "error", "is_fallback": False}