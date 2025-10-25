# HIL Layer Service

The Human-in-the-Loop (HIL) Layer is a service that manages the review process for uncertain or low-confidence classifications. It allows human experts to review and correct machine learning model predictions, creating a feedback loop that improves model accuracy over time.

## Features

- Escalation of classifications for human review
- Queue management for pending reviews
- Review submission and tracking
- Training data collection from human reviews
- Statistics and monitoring
- Integration with PostgreSQL database

## API Endpoints

### Escalation

```http
POST /escalate
```

Escalates a classification for human review. Example request:

```json
{
  "categorizer_id": "my-classifier",
  "text": "text to review",
  "suggested_category": "category-a",
  "suggested_confidence": 0.45,
  "context": {
    "source": "api",
    "user_id": "12345"
  }
}
```

### Review Management

```http
GET /pending
```

Returns pending reviews, optionally filtered by categorizer.

```http
POST /review/{review_id}
```

Submit a human review. Example request:

```json
{
  "human_category": "correct-category",
  "human_notes": "Updated due to context",
  "reviewed_by": "expert1"
}
```

```http
GET /reviewed
```

Returns completed reviews, optionally filtered by categorizer.

### Statistics

```http
GET /stats/{categorizer_id}
```

Returns HIL statistics for a specific categorizer.

### Health Check

```http
GET /health
```

Returns service health status.

## Database Schema

### HILReview Table
- `id`: UUID primary key
- `categorizer_id`: Reference to categorizer
- `text`: Text being reviewed
- `suggested_category`: Model's prediction
- `suggested_confidence`: Model's confidence
- `context`: JSON context data
- `status`: Review status (pending/reviewed)
- `human_category`: Human-assigned category
- `human_notes`: Review notes
- `reviewed_by`: Reviewer identifier
- `reviewed_at`: Review timestamp
- `created_at`: Creation timestamp

### TrainingSample Table
- `id`: UUID primary key
- `categorizer_id`: Reference to categorizer
- `text`: Sample text
- `category`: Assigned category
- `is_new`: New sample flag
- `created_at`: Creation timestamp

## Review Workflow

1. Low-confidence predictions are escalated via `/escalate`
2. Reviews appear in the `/pending` queue
3. Experts review and submit decisions via `/review/{id}`
4. Reviewed items are added to training data automatically
5. When enough new samples accumulate, model retraining is triggered

## Retraining Triggers

- System tracks new training samples per categorizer
- Default retraining threshold: 50 new samples
- `/stats` endpoint indicates when retraining is recommended

## Example Usage

Escalating a review:

```python
import requests

response = requests.post(
    "http://localhost:8040/escalate",
    json={
        "categorizer_id": "test-categorizer",
        "text": "ambiguous text",
        "suggested_category": "category-a",
        "suggested_confidence": 0.45
    }
)
print(response.json())
```

Submitting a review:

```python
review_id = "uuid-from-escalation"
response = requests.post(
    f"http://localhost:8040/review/{review_id}",
    json={
        "human_category": "category-b",
        "human_notes": "Corrected based on context",
        "reviewed_by": "expert1"
    }
)
print(response.json())
```

## Dependencies

- FastAPI
- SQLAlchemy
- PostgreSQL
- Pydantic
- UUID

## Integration

The HIL Layer service integrates with:

- Orchestrator for triggering model retraining
- PostgreSQL for review data storage
- API Gateway for external access
- Other classification services (XGBoost, LLM) for receiving escalations