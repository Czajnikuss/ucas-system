#!/usr/bin/env python3
"""
Generate README files for UCAS System
Safe string handling - no escaping issues!
"""

import os
from pathlib import Path

# Create HIL README
hil_readme = """# UCAS HIL Layer - Human-in-the-Loop Review Service

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
"""

# Create Main README
main_readme = """# UCAS System - AI-Driven Citizen Feedback Analysis

Complete microservices system for real-time classification and human-in-the-loop review of citizen feedback.

## 🏗️ Architecture

```
┌─────────────────┐
│   Categorizer   │ (AI Classification)
│    :8001        │
└────────┬────────┘
         │ (Escalate)
         ▼
┌─────────────────┐
│   HIL Layer     │ (Human Review)
│    :8040        │
└────────┬────────┘
         │ (Webhooks)
         ▼
┌─────────────────┐
│   External      │ (Client Systems)
│   Webhooks      │
└─────────────────┘
```

## 🚀 Quick Start

```bash
podman compose up -d
podman compose ps
podman compose logs -f hil-layer
```

## 📡 Main Services

| Service | Port | Purpose |
|---------|------|---------|
| **Categorizer** | 8001 | AI classification |
| **HIL Layer** | 8040 | Human review |
| **PostgreSQL** | 5432 | Data storage |

## 🔄 Data Flow

1. Classification Request → Categorizer
2. Low Confidence → Escalate to HIL
3. Human Review → HIL Layer
4. Webhook Event → External systems
5. Training Update → New samples

## 📚 API Documentation

- **Categorizer Swagger:** http://localhost:8001/swagger
- **HIL Swagger:** http://localhost:8040/swagger

## 🔌 Webhook Integration

```bash
curl -X POST "http://localhost:8040/webhooks/register?name=MySystem&url=https://myapi.com/webhook"
```

Webhook payload:
```json
{
  "event": "hil.review.pending",
  "review_id": "uuid",
  "categorizer_id": "cat-001",
  "text": "Citizen feedback",
  "suggested_category": "COMPLAINT",
  "suggested_confidence": 0.42
}
```

## 📊 Database

Schema automatically created via `init.sql`:
- Categorizers & configurations
- Training samples with embeddings
- Classifications & cascade
- HIL reviews & feedback
- Webhook endpoints & history

## 🧪 Testing

```bash
curl http://localhost:8040/health
curl http://localhost:8040/webhooks
```

## 📦 Development

```bash
podman compose build
podman compose logs -f
podman compose down
podman volume prune
```

---
**Status:** Production Ready (v0.1)  
**Last Updated:** Nov 2025
"""

# Ensure directory exists
Path("services/hil-layer").mkdir(parents=True, exist_ok=True)

# Write files
with open("services/hil-layer/README.md", "w", encoding="utf-8") as f:
    f.write(hil_readme)

with open("README.md", "w", encoding="utf-8") as f:
    f.write(main_readme)

print("✅ README.md created")
print("✅ services/hil-layer/README.md created")
print("\n📚 Documentation files generated successfully!")
print("\nFiles are ready in your repo!")
