# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy import create_engine, Column, String, DateTime, Float, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
import uuid
import os

app = FastAPI(
    title="UCAS HIL Layer",
    version="1.0.0",
    description="Human-in-the-Loop review service",
    docs_url="/swagger"
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db"
)

Base = declarative_base()

# Define models locally (lightweight duplication for service independence)
class Categorizer(Base):
    __tablename__ = "categorizers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    hil_reviews = relationship("HILReview", back_populates="categorizer")

class HILReview(Base):
    __tablename__ = "hil_reviews"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), ForeignKey("categorizers.id"), nullable=False)
    text = Column(Text, nullable=False)
    suggested_category = Column(String(255))
    suggested_confidence = Column(Float)
    context = Column(JSONB)
    status = Column(String(50), default='pending')
    human_category = Column(String(255))
    human_notes = Column(Text)
    reviewed_by = Column(String(255))
    reviewed_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    categorizer = relationship("Categorizer", back_populates="hil_reviews")

class TrainingSample(Base):
    __tablename__ = "training_samples"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), ForeignKey("categorizers.id"), nullable=False)
    text = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    is_new = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class EscalateRequest(BaseModel):
    categorizer_id: str
    text: str
    suggested_category: Optional[str] = None
    suggested_confidence: Optional[float] = None
    context: Optional[Dict] = None

class ReviewRequest(BaseModel):
    human_category: str
    human_notes: Optional[str] = None
    reviewed_by: Optional[str] = "admin"

class HILResponse(BaseModel):
    status: str
    review_id: str
    queue_position: Optional[int] = None
    message: str


@app.get("/")
async def root():
    return {"service": "UCAS HIL Layer", "status": "running", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/escalate", response_model=HILResponse)
async def escalate_to_hil(request: EscalateRequest, db: Session = Depends(get_db)):
    """Escalate classification to human review"""
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == request.categorizer_id) |
        (Categorizer.name == request.categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    hil_review = HILReview(
        categorizer_id=categorizer.id,
        text=request.text,
        suggested_category=request.suggested_category,
        suggested_confidence=request.suggested_confidence,
        context=request.context,
        status='pending'
    )
    
    db.add(hil_review)
    db.commit()
    db.refresh(hil_review)
    
    queue_position = db.query(HILReview).filter(
        HILReview.categorizer_id == categorizer.id,
        HILReview.status == 'pending',
        HILReview.created_at <= hil_review.created_at
    ).count()
    
    return HILResponse(
        status="pending_review",
        review_id=str(hil_review.id),
        queue_position=queue_position,
        message="Classification escalated to human review"
    )


@app.get("/pending")
async def get_pending_reviews(
    categorizer_id: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get pending HIL reviews"""
    query = db.query(HILReview).filter(HILReview.status == 'pending')
    
    if categorizer_id:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == categorizer_id) |
            (Categorizer.name == categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        query = query.filter(HILReview.categorizer_id == categorizer.id)
    
    reviews = query.order_by(HILReview.created_at.asc()).limit(limit).all()
    
    return [
        {
            "review_id": str(r.id),
            "categorizer_id": r.categorizer.categorizer_id,
            "categorizer_name": r.categorizer.name,
            "text": r.text,
            "suggested_category": r.suggested_category,
            "suggested_confidence": r.suggested_confidence,
            "context": r.context,
            "created_at": r.created_at.isoformat()
        }
        for r in reviews
    ]


@app.post("/review/{review_id}")
async def submit_review(
    review_id: str,
    request: ReviewRequest,
    db: Session = Depends(get_db)
):
    """Submit human review and add to training data"""
    hil_review = db.query(HILReview).filter(HILReview.id == review_id).first()
    
    if not hil_review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    if hil_review.status != 'pending':
        raise HTTPException(status_code=400, detail="Review already processed")
    
    hil_review.status = 'reviewed'
    hil_review.human_category = request.human_category
    hil_review.human_notes = request.human_notes
    hil_review.reviewed_by = request.reviewed_by
    hil_review.reviewed_at = datetime.utcnow()
    
    training_sample = TrainingSample(
        categorizer_id=hil_review.categorizer_id,
        text=hil_review.text,
        category=request.human_category,
        is_new=True
    )
    db.add(training_sample)
    
    db.commit()
    
    new_samples_count = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == hil_review.categorizer_id,
        TrainingSample.is_new == True
    ).count()
    
    return {
        "status": "reviewed",
        "review_id": str(hil_review.id),
        "human_category": request.human_category,
        "added_to_training": True,
        "new_samples_count": new_samples_count,
        "retrain_threshold": 50,
        "should_retrain": new_samples_count >= 50
    }


@app.get("/reviewed")
async def get_reviewed(
    categorizer_id: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get reviewed HIL items"""
    query = db.query(HILReview).filter(HILReview.status == 'reviewed')
    
    if categorizer_id:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == categorizer_id) |
            (Categorizer.name == categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        query = query.filter(HILReview.categorizer_id == categorizer.id)
    
    reviews = query.order_by(HILReview.reviewed_at.desc()).limit(limit).all()
    
    return [
        {
            "review_id": str(r.id),
            "categorizer_id": r.categorizer.categorizer_id,
            "text": r.text,
            "suggested_category": r.suggested_category,
            "suggested_confidence": r.suggested_confidence,
            "human_category": r.human_category,
            "human_notes": r.human_notes,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "created_at": r.created_at.isoformat()
        }
        for r in reviews
    ]


@app.get("/stats/{categorizer_id}")
async def get_hil_stats(categorizer_id: str, db: Session = Depends(get_db)):
    """Get HIL statistics for categorizer"""
    categorizer = db.query(Categorizer).filter(
        (Categorizer.categorizer_id == categorizer_id) |
        (Categorizer.name == categorizer_id)
    ).first()
    
    if not categorizer:
        raise HTTPException(status_code=404, detail="Categorizer not found")
    
    pending = db.query(HILReview).filter(
        HILReview.categorizer_id == categorizer.id,
        HILReview.status == 'pending'
    ).count()
    
    reviewed = db.query(HILReview).filter(
        HILReview.categorizer_id == categorizer.id,
        HILReview.status == 'reviewed'
    ).count()
    
    new_samples = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer.id,
        TrainingSample.is_new == True
    ).count()
    
    return {
        "categorizer_id": categorizer.categorizer_id,
        "categorizer_name": categorizer.name,
        "pending_reviews": pending,
        "reviewed_count": reviewed,
        "new_training_samples": new_samples,
        "retrain_threshold": 50,
        "should_retrain": new_samples >= 50
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8040)
