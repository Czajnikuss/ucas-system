from sqlalchemy import create_engine, Column, String, Text, Integer, Float, Boolean, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime
import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    # Default fallback should use the ucas user created by services/postgres/init.sql
    "postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models matching our schema
class Categorizer(Base):
    __tablename__ = "categorizers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(String(50), default='training')

class TrainingData(Base):
    __tablename__ = "training_data"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), nullable=False)
    text = Column(Text, nullable=False)
    category = Column(String(255), nullable=False)
    embedding = Column(String)  # Will store vector as string for now
    meta = Column('metadata', JSON)  # Renamed to 'meta' in code, but 'metadata' in DB
    is_new = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class CategorizationLog(Base):
    __tablename__ = "categorization_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    categorizer_id = Column(UUID(as_uuid=True), nullable=False)
    input_text = Column(Text, nullable=False)
    predicted_category = Column(String(255))
    confidence = Column(Float)
    layer_used = Column(String(50))
    layer_confidences = Column(JSON)
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()