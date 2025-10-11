# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import asyncio
import re
from unidecode import unidecode
from sqlalchemy import text


from models.database import init_db, get_db, Categorizer, TrainingSample, Classification

app = FastAPI(
    title="UCAS Orchestrator",
    version="3.0.0",
    description="Orchestrator with database persistence"
)

# Initialize database on startup
@app.on_event("startup")
async def startup_event():
    init_db()
    print("Database initialized")

TAGS_LAYER = "http://tags-layer:8010"
XGBOOST_LAYER = "http://xgboost-layer:8020"
LLM_LAYER = "http://llm-layer:8030"

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

@app.get("/")
async def root():
    return {
        "service": "UCAS Orchestrator",
        "version": "3.0.0",
        "features": ["persistence", "cascade", "fallback"]
    }

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    layers_health = {}
    async with httpx.AsyncClient() as client:
        for name, url in [("tags", TAGS_LAYER), ("xgboost", XGBOOST_LAYER), ("llm", LLM_LAYER)]:
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                layers_health[name] = "healthy" if response.status_code == 200 else "error"
            except:
                layers_health[name] = "unreachable"
    
    # Check database - FIX THIS
    try:
        db.execute(text("SELECT 1"))  # Need to import text
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {"status": "healthy", "layers": layers_health, "database": db_status}

def generate_slug(name: str) -> str:
    """Generate URL-safe slug from name"""
    slug = unidecode(name.lower())
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


@app.post("/train")
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
        "llm_config": request.llm_config
    }
    
    # Save training samples
    for sample in request.training_data:
        training_sample = TrainingSample(
            categorizer_id=categorizer.id,
            text=sample["text"],
            category=sample["category"]
        )
        db.add(training_sample)
    
    db.commit()
    
    # Train layers
    results = {}
    async with httpx.AsyncClient() as client:
        if "tags" in request.layers:
            tags_request = {
                "categorizer_id": categorizer_id,
                "training_data": request.training_data,
                **(request.tags_config or {})
            }
            try:
                response = await client.post(f"{TAGS_LAYER}/train", json=tags_request, timeout=30.0)
                results["tags"] = response.json()
            except Exception as e:
                results["tags"] = {"error": str(e)}
        
        if "xgboost" in request.layers:
            xgb_request = {
                "categorizer_id": categorizer_id,
                "training_data": request.training_data,
                **(request.xgboost_config or {})
            }
            try:
                response = await client.post(f"{XGBOOST_LAYER}/train", json=xgb_request, timeout=60.0)
                results["xgboost"] = response.json()
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
                response = await client.post(f"{LLM_LAYER}/train", json=llm_request, timeout=60.0)
                results["llm"] = response.json()
            except Exception as e:
                results["llm"] = {"error": str(e)}
    
    return {
        "status": "trained",
        "categorizer_id": categorizer_id,
        "name": name,
        "categories": categories,
        "fallback_category": request.fallback_category,
        "training_samples": len(request.training_data),
        "layers": request.layers,
        "results": results
    }


@app.post("/classify")
async def classify(request: ClassifyRequest, db: Session = Depends(get_db)):
    # Try by categorizer_id first, then by name
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == request.categorizer_id) |
        (Categorizer.name == request.categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(
            status_code=404, 
            detail=f"Categorizer '{request.categorizer_id}' not found by ID or name"
        )
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found. Train it first.")
    
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
    """Cascade strategy: Tags → XGBoost → LLM → HIL"""
    cascade_results = {}
    
    # Get categorizer config for HIL thresholds
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    # Default HIL thresholds (can be overridden in categorizer.config)
    hil_config = categorizer.config.get('hil_config', {}) if categorizer and categorizer.config else {}
    tags_threshold = hil_config.get('tags_threshold', 0.7)
    xgboost_threshold = hil_config.get('xgboost_threshold', 0.7)
    llm_threshold = hil_config.get('llm_threshold', 0.8)
    hil_enabled = hil_config.get('enabled', True)
    
    async with httpx.AsyncClient() as client:
        # Layer 1: Tags
        try:
            response = await client.post(
                f"{TAGS_LAYER}/classify",
                json={"categorizer_id": categorizer_id, "text": text},
                timeout=5.0
            )
            tags_result = response.json()
            cascade_results["tags"] = tags_result
            
            if tags_result.get("confidence") == 1.0 and tags_result.get("category"):
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
        
        # Layer 2: XGBoost
        try:
            response = await client.post(
                f"{XGBOOST_LAYER}/classify",
                json={"categorizer_id": categorizer_id, "text": text},
                timeout=10.0
            )
            xgb_result = response.json()
            cascade_results["xgboost"] = xgb_result
            
            if xgb_result.get("confidence", 0) > 0.7 and xgb_result.get("category"):
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
        
        # Layer 3: LLM
        try:
            response = await client.post(
                f"{LLM_LAYER}/classify",
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
                        "http://hil-layer:8040/escalate",
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
            return {
                "category": None,
                "confidence": 0.0,
                "method": "error",
                "reasoning": "All layers failed",
                "cascade_results": cascade_results,
                "is_fallback": False
            }

async def classify_all(categorizer_id: str, text: str) -> Dict:
    """Parallel execution, best result"""
    async with httpx.AsyncClient() as client:
        tasks = [
            client.post(f"{TAGS_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=5.0),
            client.post(f"{XGBOOST_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=10.0),
            client.post(f"{LLM_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=60.0)
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
            response = await client.post(f"{TAGS_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=2.0)
            result = response.json()
            if result.get("category"):
                return {"category": result["category"], "confidence": result["confidence"], "method": "tags", "reasoning": "Fast", "is_fallback": False}
        except:
            pass
        
        try:
            response = await client.post(f"{XGBOOST_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=10.0)
            result = response.json()
            if result.get("category"):
                return {"category": result["category"], "confidence": result["confidence"], "method": "xgboost", "reasoning": "ML", "is_fallback": False}
        except:
            pass
        
        try:
            response = await client.post(f"{LLM_LAYER}/classify", json={"categorizer_id": categorizer_id, "text": text}, timeout=60.0)
            result = response.json()
            return {"category": result.get("category"), "confidence": result.get("confidence", 0.5), "method": "llm", "reasoning": result.get("reasoning", ""), "is_fallback": result.get("is_fallback", False)}
        except Exception as e:
            return {"category": None, "confidence": 0.0, "method": "error", "reasoning": str(e), "is_fallback": False}

@app.get("/categorizers")
async def list_categorizers(db: Session = Depends(get_db)):
    """List all categorizers"""
    categorizers = db.query(Categorizer).all()
    return [
        {
            "categorizer_id": c.categorizer_id,
            "name": c.name,
            "categories": c.categories,
            "fallback_category": c.fallback_category,
            "training_samples": len(c.training_samples),
            "created_at": c.created_at.isoformat()
        }
        for c in categorizers
    ]

@app.get("/categorizers/{categorizer_id}")
async def get_categorizer(categorizer_id: str, db: Session = Depends(get_db)):
    """Get categorizer details"""
    categorizer = db.query(Categorizer).filter(
        Categorizer.categorizer_id == categorizer_id
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    return {
        "categorizer_id": categorizer.categorizer_id,
        "name": categorizer.name,
        "description": categorizer.description,
        "categories": categorizer.categories,
        "fallback_category": categorizer.fallback_category,
        "layers": categorizer.layers,
        "training_samples": len(categorizer.training_samples),
        "total_classifications": len(categorizer.classifications),
        "created_at": categorizer.created_at.isoformat(),
        "updated_at": categorizer.updated_at.isoformat()
    }

@app.get("/categorizers/{categorizer_id}/history")
async def get_classification_history(
    categorizer_id: str,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get classification history"""
    categorizer = db.query(Categorizer).filter(
        Categorizer.categorizer_id == categorizer_id
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    classifications = db.query(Classification).filter(
        Classification.categorizer_id == categorizer.id
    ).order_by(Classification.created_at.desc()).limit(limit).all()
    
    return [
        {
            "text": c.text,
            "category": c.predicted_category,
            "confidence": c.confidence,
            "method": c.method,
            "is_fallback": c.is_fallback,
            "processing_time_ms": c.processing_time_ms,
            "created_at": c.created_at.isoformat()
        }
        for c in classifications
    ]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
