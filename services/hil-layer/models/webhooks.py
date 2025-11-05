# services/hil-layer/models/webhooks.py
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Integer, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime

Base = declarative_base()

class Webhook(Base):
    """
    Webhook registration for HIL events
    
    v0.1: No role filtering
    v1.0: Add role_required, categorizer_whitelist
    """
    __tablename__ = "webhooks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=None)
    url = Column(String(2048), nullable=False, unique=True)  # External endpoint
    
    # v0.1: No filtering
    # v1.0 fields (placeholder - not used yet):
    categorizer_filter = Column(String(255), nullable=True)  # Future: categorizer_id to filter
    role_required = Column(String(50), nullable=True)        # Future: "admin", "reviewer"
    
    # Status
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime, nullable=True)
    failed_attempts = Column(Integer, default=0)
    max_failures = Column(Integer, default=3)  # Disable after 3 failures
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    deliveries = relationship("WebhookDelivery", back_populates="webhook", cascade="all, delete-orphan")


class WebhookDelivery(Base):
    """Delivery history of webhook calls"""
    __tablename__ = "webhook_deliveries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    webhook_id = Column(UUID(as_uuid=True), ForeignKey("webhooks.id"), nullable=False)
    
    # Event details
    hil_review_id = Column(UUID(as_uuid=True), nullable=False)  # Reference to HILReview
    categorizer_id = Column(String(255), nullable=False)
    
    # Delivery status
    status = Column(String(50), default="pending")  # pending, sent, failed, retry
    response_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    
    # Relationship
    webhook = relationship("Webhook", back_populates="deliveries")
