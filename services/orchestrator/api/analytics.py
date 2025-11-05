# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from models.database import get_db, Categorizer, TrainingSample, Classification
from sqlalchemy import func

router = APIRouter()

@router.get("/categorizers/{categorizer_id}/history", tags=["Analytics"])
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

@router.get("/categorizers/{categorizer_id}/training_samples", tags=["Analytics"])
async def get_training_samples(
    categorizer_id: str,
    include_inactive: bool = False,
    db: Session = Depends(get_db)
):
    """Get training samples with quality scores"""
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(404, "Categorizer not found")
    
    query = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer.id
    )
    
    if not include_inactive:
        query = query.filter(TrainingSample.is_active == True)
    
    samples = query.order_by(TrainingSample.quality_score.desc().nullslast()).all()
    
    return [
        {
            "id": str(s.id),
            "text": s.text,
            "category": s.category,
            "quality_score": s.quality_score,
            "quality_reasoning": s.quality_reasoning,
            "is_active": s.is_active,
            "source": s.source,
            "created_at": s.created_at.isoformat()
        }
        for s in samples
    ]

@router.get("/cascade_stats/{categorizer_id}", tags=["Analytics"])
async def get_cascade_stats(categorizer_id: str, db: Session = Depends(get_db)):
    """Get cascade performance statistics"""
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(404, "Categorizer not found")
    
    # Count by method
    method_counts = db.query(
        Classification.method,
        func.count(Classification.id),
        func.avg(Classification.confidence),
        func.avg(Classification.processing_time_ms)
    ).filter(
        Classification.categorizer_id == categorizer.id
    ).group_by(Classification.method).all()
    
    return {
        "categorizer_id": categorizer_id,
        "by_method": [
            {
                "method": method,
                "count": count,
                "avg_confidence": float(avg_conf) if avg_conf else 0,
                "avg_time_ms": float(avg_time) if avg_time else 0
            }
            for method, count, avg_conf, avg_time in method_counts
        ]
    }