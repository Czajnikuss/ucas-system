# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from models.database import get_db, Categorizer, Classification, TrainingSample

router = APIRouter()


@router.get("/categorizers/{categorizer_id}/stats", tags=["Management"])
async def get_categorizer_stats(categorizer_id: str, db: Session = Depends(get_db)):
    categorizer = db.query(Categorizer).filter_by(categorizer_id=categorizer_id).first()
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
        
    total = db.query(Classification).filter_by(categorizer_id=categorizer.id).count()
    if total == 0:
        return {"total_requests": 0}
        
    methods_data = db.query(Classification.method, func.count(Classification.id)).filter_by(categorizer_id=categorizer.id).group_by(Classification.method).all()
    methods_dist = {method: count for method, count in methods_data}
    
    avg_time = db.query(func.avg(Classification.processing_time_ms)).filter_by(categorizer_id=categorizer.id).scalar()
    
    return {
        "total_requests": total,
        "method_distribution": methods_dist,
        "average_processing_time_ms": round(avg_time, 2) if avg_time else 0
    }

@router.get("/categorizers/{categorizer_id}/history", tags=["Management"])
async def get_categorizer_history(categorizer_id: str, limit: int = 50, db: Session = Depends(get_db)):
    categorizer = db.query(Categorizer).filter_by(categorizer_id=categorizer_id).first()
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
        
    history = db.query(Classification).filter_by(categorizer_id=categorizer.id).order_by(Classification.created_at.desc()).limit(limit).all()
    
    # Zwracamy wszystko jak leci, bez filtrowania
    return [{
        "id": str(h.id),
        "text": h.text,
        "predicted_category": h.predicted_category,
        "confidence": h.confidence,
        "method": h.method,
        "reasoning": h.reasoning,
        "is_fallback": h.is_fallback,
        "time_ms": h.processing_time_ms,
        "cascade_results": h.cascade_results,
        "created_at": h.created_at.isoformat() if h.created_at else None,
        "prompt": h.llm_prompt
    } for h in history]

@router.get("/categorizers", tags=["Management"])
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

@router.get("/categorizers/{categorizer_id}", tags=["Management"])
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

@router.delete("/categorizers/{categorizer_id}", tags=["Management"])
async def delete_categorizer(categorizer_id: str, db: Session = Depends(get_db)):
    """Delete a categorizer"""
    categorizer = db.query(Categorizer).filter(
        Categorizer.categorizer_id == categorizer_id
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    db.delete(categorizer)
    db.commit()
    
    return {"status": "deleted", "categorizer_id": categorizer_id}

@router.get("/categorizers/{categorizer_id}/export", tags=["Management"])
async def export_categorizer_data(categorizer_id: str, db: Session = Depends(get_db)):
    categorizer = db.query(Categorizer).filter_by(categorizer_id=categorizer_id).first()
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
        
    samples = db.query(TrainingSample).filter_by(categorizer_id=categorizer.id).all()
    
    payload = {
        "name": categorizer.name,
        "description": categorizer.description or "",
        "layers": categorizer.layers,
        "fallback_category": categorizer.fallback_category,
        "training_data": [{"text": s.text, "category": s.category} for s in samples]
    }
    
    # Dołączenie oryginalnych konfiguracji z kolumny JSONB
    if categorizer.config:
        for key, value in categorizer.config.items():
            payload[key] = value
            
    return payload