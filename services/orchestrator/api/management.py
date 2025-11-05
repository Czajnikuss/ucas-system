# -*- coding: utf-8 -*-
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from models.database import get_db, Categorizer

router = APIRouter()

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