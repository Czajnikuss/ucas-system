# models/database.py
from sqlalchemy import create_engine, Column, String, DateTime, Float, Boolean, Text, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import sessionmaker, relationship
import uuid
from datetime import datetime
import os


Base = declarative_base()


class Categorizer(Base):
    __tablename__ = "categorizers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255))
    description = Column(Text)
    categories = Column(JSONB)
    fallback_category = Column(String(100))
    layers = Column(JSONB)
    config = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    training_samples = relationship("TrainingSample", back_populates="categorizer", cascade="all, delete-orphan")
    classifications = relationship("Classification", back_populates="categorizer")
    hil_reviews = relationship("HILReview", back_populates="categorizer")


class TrainingSample(Base):
    __tablename__ = "training_samples"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), ForeignKey("categorizers.id"), nullable=False)
    text = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    is_new = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    categorizer = relationship("Categorizer", back_populates="training_samples")


class Classification(Base):
    __tablename__ = "classifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), ForeignKey("categorizers.id"), nullable=False)
    text = Column(Text, nullable=False)
    predicted_category = Column(String(100))
    confidence = Column(Float)
    method = Column(String(50))
    is_fallback = Column(Boolean, default=False)
    processing_time_ms = Column(Float)
    cascade_results = Column(JSONB)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    categorizer = relationship("Categorizer", back_populates="classifications")


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


# Database connection from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db"
)


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
