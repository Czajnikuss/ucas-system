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
import httpx
from webhooks import WebhookService

app = FastAPI(
    title="UCAS HIL Layer",
    version="1.1.0",
    description="Human-in-the-Loop review service",
    docs_url="/swagger"
)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db"
)

Base = declarative_base()

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

class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    url = Column(String(2048), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class WebhookDelivery(Base):
    __tablename__ = "webhook_deliveries"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)
    hil_review_id = Column(String(255))
    categorizer_id = Column(String(255))
    status = Column(String(50))
    response_code = Column(String(10))
    sent_at = Column(DateTime, default=datetime.utcnow)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

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

class PendingReviewResponse(BaseModel):
    review_id: str
    categorizer_id: str
    text: str
    suggested_category: Optional[str]
    suggested_confidence: float
    status: str
    created_at: Optional[str]

class ReviewedItemResponse(BaseModel):
    review_id: str
    categorizer_id: str
    text: str
    suggested_category: Optional[str]
    suggested_confidence: Optional[float]
    human_category: Optional[str]
    human_notes: Optional[str]
    reviewed_by: Optional[str]
    reviewed_at: Optional[str]
    created_at: str

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/escalate", response_model=HILResponse)
async def escalate_to_hil(request: EscalateRequest, db: Session = Depends(get_db)):
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
    
    webhook_service = WebhookService(db)
    await webhook_service.trigger_webhooks(
        hil_review_id=str(hil_review.id),
        categorizer_id=request.categorizer_id,
        text=request.text,
        suggested_category=request.suggested_category or "Unknown",
        suggested_confidence=request.suggested_confidence or 0.0
    )
    
    return HILResponse(
        status="pending_review",
        review_id=str(hil_review.id),
        queue_position=queue_position,
        message="Classification escalated to human review"
    )

@app.get("/pending", response_model=List[PendingReviewResponse])
async def get_pending_reviews(db: Session = Depends(get_db)):
    """Get all pending HIL reviews directly via ORM"""
    reviews = db.query(HILReview).filter(HILReview.status == 'pending').order_by(HILReview.created_at.desc()).all()
    
    return [
        PendingReviewResponse(
            review_id=str(r.id),
            categorizer_id=r.categorizer.categorizer_id,
            text=r.text,
            suggested_category=r.suggested_category,
            suggested_confidence=r.suggested_confidence or 0.0,
            status=r.status,
            created_at=r.created_at.isoformat() if r.created_at else None
        )
        for r in reviews
    ]

@app.post("/review/{review_id}")
async def submit_review(review_id: str, request: ReviewRequest, db: Session = Depends(get_db)):
    """Submit human review and inject back to training data"""
    review = db.query(HILReview).filter(HILReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    if review.status == 'reviewed':
        raise HTTPException(status_code=400, detail="Review already completed")
        
    review.human_category = request.human_category
    review.human_notes = request.human_notes
    review.reviewed_by = request.reviewed_by
    review.status = 'reviewed'
    review.reviewed_at = datetime.utcnow()
    
    new_sample = TrainingSample(
        categorizer_id=review.categorizer_id,
        text=review.text,
        category=request.human_category,
        is_new=True
    )
    db.add(new_sample)
    db.commit()
    
    return {"status": "reviewed", "review_id": review_id, "new_sample_id": str(new_sample.id)}

@app.get("/reviewed", response_model=List[ReviewedItemResponse])
async def get_reviewed(categorizer_id: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db)):
    query = db.query(HILReview).filter(HILReview.status == 'reviewed')
    
    if categorizer_id:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == categorizer_id) | (Categorizer.name == categorizer_id)
        ).first()
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        query = query.filter(HILReview.categorizer_id == categorizer.id)
    
    reviews = query.order_by(HILReview.reviewed_at.desc()).limit(limit).all()
    
    return [
        ReviewedItemResponse(
            review_id=str(r.id),
            categorizer_id=r.categorizer.categorizer_id,
            text=r.text,
            suggested_category=r.suggested_category,
            suggested_confidence=r.suggested_confidence,
            human_category=r.human_category,
            human_notes=r.human_notes,
            reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
            created_at=r.created_at.isoformat()
        )
        for r in reviews
    ]

# ... webhook endpoints ...
@app.get("/webhooks")
async def list_webhooks(db: Session = Depends(get_db)):
    webhook_service = WebhookService(db)
    webhooks = webhook_service.list_webhooks()
    return {"count": len(webhooks), "webhooks": webhooks}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8040)