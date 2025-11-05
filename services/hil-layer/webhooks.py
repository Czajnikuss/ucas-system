# services/hil-layer/webhooks.py
import httpx
import asyncio
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

class WebhookService:
    def __init__(self, db: Session):
        self.db = db
    
    async def trigger_webhooks(self, hil_review_id: str, categorizer_id: str, text: str, suggested_category: str, suggested_confidence: float):
        try:
            webhooks = self.db.execute(text("SELECT id, url FROM webhooks WHERE is_active = TRUE")).fetchall()
            if not webhooks:
                return
            payload = {"event": "hil.review.pending", "version": "0.1", "timestamp": datetime.utcnow().isoformat(), "review_id": str(hil_review_id), "categorizer_id": categorizer_id, "text": text, "suggested_category": suggested_category, "suggested_confidence": suggested_confidence}
            asyncio.create_task(self._send_all_webhooks(webhooks, payload))
        except Exception as e:
            logger.error(f"Webhook trigger error: {str(e)}")
    
    async def _send_all_webhooks(self, webhooks: List, payload: dict):
        tasks = [self._send_webhook(webhook_id, url, payload) for webhook_id, url in webhooks]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_webhook(self, webhook_id: str, url: str, payload: dict):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                status = "sent" if response.status_code < 400 else "failed"
                self.db.execute(text("INSERT INTO webhook_deliveries (webhook_id, hil_review_id, categorizer_id, status, response_code, sent_at) VALUES (:webhook_id, :hil_review_id, :categorizer_id, :status, :response_code, NOW())"), {"webhook_id": webhook_id, "hil_review_id": payload["review_id"], "categorizer_id": payload["categorizer_id"], "status": status, "response_code": response.status_code})
                self.db.commit()
        except Exception as e:
            logger.error(f"Webhook failed: {str(e)}")
    
    def register_webhook(self, name: str, url: str, description: Optional[str] = None):
        # Check for duplicate URL
        existing = self.db.execute(
            text("SELECT id FROM webhooks WHERE url = :url AND is_active = TRUE"),
            {"url": url}
        ).fetchone()
        
        if existing:
            raise ValueError(f"Webhook with URL {url} already registered")
        
        webhook_id = str(__import__('uuid').uuid4())
        self.db.execute(
            text("INSERT INTO webhooks (id, name, url, description, is_active) VALUES (:id, :name, :url, :description, TRUE)"),
            {"id": webhook_id, "name": name, "url": url, "description": description}
        )
        self.db.commit()
        return {"webhook_id": webhook_id, "status": "registered"}
    
    def list_webhooks(self) -> List[dict]:
        webhooks = self.db.execute(text("SELECT id, name, url, is_active FROM webhooks WHERE is_active = TRUE")).fetchall()
        return [{"webhook_id": str(w[0]), "name": w[1], "url": w[2]} for w in webhooks]
    
    def delete_webhook(self, webhook_id: str):
        self.db.execute(text("DELETE FROM webhooks WHERE id = :id"), {"id": webhook_id})
        self.db.commit()
        return {"status": "deleted"}
    
    def get_delivery_history(self, webhook_id: str, limit: int = 50):
        deliveries = self.db.execute(text("SELECT id, hil_review_id, status, response_code, sent_at FROM webhook_deliveries WHERE webhook_id = :webhook_id ORDER BY sent_at DESC LIMIT :limit"), {"webhook_id": webhook_id, "limit": limit}).fetchall()
        return [{"delivery_id": str(d[0]), "status": d[2], "response_code": d[3]} for d in deliveries]