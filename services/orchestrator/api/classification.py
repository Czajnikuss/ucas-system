# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
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

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    method: str
    reasoning: Optional[str] = None
    processing_time_ms: float
    is_fallback: bool = False

@router.post("/classify", tags=["Classification"])
async def classify(request: ClassifyRequest, db: Session = Depends(get_db)):
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == request.categorizer_id) |
        (Categorizer.name == request.categorizer_id)
    ).one_or_none()
    
    if not categorizer:
        raise HTTPException(
            status_code=404,
            detail=f"Categorizer '{request.categorizer_id}' not found by ID or name"
        )

    start_time = datetime.now()
    
    # Run classification
    if request.strategy == "cascade":
        result = await classify_cascade(request.categorizer_id, request.text, db)
    elif request.strategy == "all":
        result = await classify_all(request.categorizer_id, request.text)
    elif request.strategy == "fastest":
        result = await classify_fastest(request.categorizer_id, request.text)
    else:
        raise HTTPException(status_code=400, detail="Invalid strategy")
    
    processing_time = (datetime.now() - start_time).total_seconds() * 1000
    result["processing_time_ms"] = processing_time
    
    # Save to history
    if request.save_to_history:
        classification = Classification(
            categorizer_id=categorizer.id,
            text=request.text,
            predicted_category=result.get("category"),
            confidence=result.get("confidence"),
            method=result.get("method"),
            is_fallback=result.get("is_fallback", False),
            processing_time_ms=processing_time,
            cascade_results=result.get("cascade_results")
        )
        db.add(classification)
        db.commit()
    
    return ClassifyResponse(**result)

async def classify_cascade(categorizer_id: str, text: str, db: Session) -> Dict:
    """Cascade strategy: Tags → XGBoost → LLM → HIL (skip layers not in config)"""
    cascade_results = {}
    
    # Get categorizer config for HIL thresholds
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    if not categorizer:
        return {
            "category": None,
            "confidence": 0.0,
            "method": "error",
            "reasoning": "Categorizer not found in database",
            "cascade_results": {},
            "is_fallback": False
        }
    
    # Get configured layers
    configured_layers = categorizer.layers or []
    
    # Default HIL thresholds (can be overridden in categorizer.config)
    hil_config = categorizer.config.get('hil_config', {}) if categorizer.config else {}
    tags_threshold = hil_config.get('tags_threshold', 0.7)
    xgboost_threshold = hil_config.get('xgboost_threshold', 0.7)
    llm_threshold = hil_config.get('llm_threshold', 0.8)
    hil_enabled = hil_config.get('enabled', True)
    
    async with httpx.AsyncClient() as client:
        # Layer 1: Tags (only if configured)
        if "tags" in configured_layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.tags.url')}/classify",
                    json={"categorizer_id": categorizer_id, "text": text},
                    timeout=5.0
                )
                tags_result = response.json()
                cascade_results["tags"] = tags_result
                
                if tags_result.get("confidence", 0) >= tags_threshold and tags_result.get("category"):
                    return {
                        "category": tags_result["category"],
                        "confidence": tags_result["confidence"],
                        "method": "tags",
                        "reasoning": "Exact keyword match",
                        "cascade_results": cascade_results,
                        "is_fallback": False
                    }
            except Exception as e:
                cascade_results["tags"] = {"error": str(e)}
        
        # Layer 2: XGBoost (only if configured)
        if "xgboost" in configured_layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.xgboost.url')}/classify",
                    json={"categorizer_id": categorizer_id, "text": text},
                    timeout=10.0
                )
                xgb_result = response.json()
                cascade_results["xgboost"] = xgb_result
                
                # FIXED: Use threshold from DB, not hardcoded 0.7
                if xgb_result.get("confidence", 0) >= xgboost_threshold and xgb_result.get("category"):
                    return {
                        "category": xgb_result["category"],
                        "confidence": xgb_result["confidence"],
                        "method": "xgboost",
                        "reasoning": "High confidence ML prediction",
                        "cascade_results": cascade_results,
                        "is_fallback": False
                    }
            except Exception as e:
                cascade_results["xgboost"] = {"error": str(e)}
        
        # Layer 3: LLM (only if configured)
        if "llm" in configured_layers:
            try:
                response = await client.post(
                    f"{config.get('orchestrator.layers.llm.url')}/classify",
                    json={"categorizer_id": categorizer_id, "text": text},
                    timeout=60.0
                )
                llm_result = response.json()
                cascade_results["llm"] = llm_result
                
                llm_confidence = llm_result.get("confidence", 0.5)
                
                # Check if we should escalate to HIL
                tags_conf = cascade_results.get("tags", {}).get("confidence", 0)
                xgb_conf = cascade_results.get("xgboost", {}).get("confidence", 0)
                
                should_escalate_to_hil = hil_enabled and all([
                    tags_conf < tags_threshold,
                    xgb_conf < xgboost_threshold,
                    llm_confidence < llm_threshold
                ])
                
                if should_escalate_to_hil:
                    # Layer 4: HIL Escalation
                    try:
                        hil_response = await client.post(
                            f"{config.get('orchestrator.layers.hil.url')}/escalate",
                            json={
                                "categorizer_id": categorizer_id,
                                "text": text,
                                "suggested_category": llm_result.get("category"),
                                "suggested_confidence": llm_confidence,
                                "context": {
                                    "tags": cascade_results.get("tags"),
                                    "xgboost": cascade_results.get("xgboost"),
                                    "llm": llm_result
                                }
                            },
                            timeout=5.0
                        )
                        hil_result = hil_response.json()
                        cascade_results["hil"] = hil_result
                        
                        return {
                            "category": None,
                            "confidence": 0.0,
                            "method": "hil_pending",
                            "reasoning": f"Low confidence across all layers - escalated to human review (Review ID: {hil_result.get('review_id')})",
                            "cascade_results": cascade_results,
                            "is_fallback": False,
                            "hil_review_id": hil_result.get("review_id"),
                            "queue_position": hil_result.get("queue_position")
                        }
                    except Exception as e:
                        cascade_results["hil"] = {"error": str(e)}
                
                # Return LLM result if HIL disabled or escalation failed
                return {
                    "category": llm_result.get("category"),
                    "confidence": llm_confidence,
                    "method": "llm",
                    "reasoning": llm_result.get("reasoning", ""),
                    "cascade_results": cascade_results,
                    "is_fallback": llm_result.get("is_fallback", False)
                }
            except Exception as e:
                cascade_results["llm"] = {"error": str(e)}
        
        # If we get here, all configured layers failed or returned low confidence
        return {
            "category": None,
            "confidence": 0.0,
            "method": "error",
            "reasoning": "All configured layers failed or returned low confidence",
            "cascade_results": cascade_results,
            "is_fallback": False
        }


async def classify_all(categorizer_id: str, text: str) -> Dict:
    """Parallel execution, best result"""
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
        
        return {
            "category": None,
            "confidence": 0.0,
            "method": "error",
            "reasoning": "All layers failed",
            "cascade_results": all_results,
            "is_fallback": False
        }

async def classify_fastest(categorizer_id: str, text: str) -> Dict:
    """First successful result"""
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{config.get('orchestrator.layers.tags.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=2.0)
            result = response.json()
            if result.get("category"):
                return {"category": result["category"], "confidence": result["confidence"], "method": "tags", "reasoning": "Fast", "is_fallback": False}
        except:
            pass
        
        try:
            response = await client.post(f"{config.get('orchestrator.layers.xgboost.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=10.0)
            result = response.json()
            if result.get("category"):
                return {"category": result["category"], "confidence": result["confidence"], "method": "xgboost", "reasoning": "ML", "is_fallback": False}
        except:
            pass
        
        try:
            response = await client.post(f"{config.get('orchestrator.layers.llm.url')}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=60.0)
            result = response.json()
            return {"category": result.get("category"), "confidence": result.get("confidence", 0.5), "method": "llm", "reasoning": result.get("reasoning", ""), "is_fallback": result.get("is_fallback", False)}
        except Exception as e:
            return {"category": None, "confidence": 0.0, "method": "error", "reasoning": str(e), "is_fallback": False}