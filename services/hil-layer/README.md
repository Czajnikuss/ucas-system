# UCAS HIL Layer - Human-in-the-Loop Review Service

Serwis do escalacji Classifications, które AI nie może zaklasyfikować. Umożliwia człowiekowi weryfikację i dodawanie nowych samples do training data.

## 🚀 Quick Start

```bash
podman compose up -d hil-layer
curl http://localhost:8040/health
```

## 📡 API Endpoints

### HIL Reviews
- **POST /escalate** - Escalate classification to human review
- **GET /pending** - Get pending reviews
- **POST /review/{review_id}** - Submit human review
- **GET /reviewed** - Get reviewed items
- **GET /stats/{categorizer_id}** - Get HIL statistics

### Webhooks (v0.1)
- **POST /webhooks/register** - Register webhook endpoint
- **GET /webhooks** - List all webhooks
- **DELETE /webhooks/{webhook_id}** - Unregister webhook
- **GET /webhooks/{webhook_id}/history** - Delivery history
- **POST /webhooks/{webhook_id}/test** - Send test payload

## 🔔 Webhook Events

When HIL review is escalated, webhook receives:
```json
{
  "event": "hil.review.pending",
  "version": "0.1",
  "timestamp": "2025-11-02T11:58:00",
  "review_id": "uuid-here",
  "categorizer_id": "cat-001",
  "text": "Review text",
  "suggested_category": "UNKNOWN",
  "suggested_confidence": 0.45
}
```

## 📊 Database Schema

- `hil_reviews` - Pending and completed reviews
- `training_samples` - New samples from human reviews
- `webhooks` - Registered webhook endpoints
- `webhook_deliveries` - Delivery history

## 🔧 Configuration

```env
DATABASE_URL=postgresql://ucas_user:ucas_password_123@postgres:5432/ucas_db
```

## 📚 API Documentation

Interactive Swagger UI: http://localhost:8040/swagger

## 🚦 Health Check

```bash
curl http://localhost:8040/health
```

## v1.0 Roadmap

- [ ] Categorizer-specific webhook filtering
- [ ] Role-based access control
- [ ] Webhook retry logic
- [ ] Delivery success rate tracking
- [ ] Batch review operations

---
**Version:** 1.0.0  
**Status:** Production Ready (v0.1 features)
