# Evaluator Service

The Evaluator service is responsible for assessing and maintaining the quality of training data in the UCAS system. It provides automated scoring of training samples, manages dataset curation, and ensures optimal dataset composition for model training.

## Features

- Automated quality scoring of training samples
- Background scoring worker
- Dataset curation pipeline
- Quality metrics tracking
- Sample archival management
- Dataset size optimization

## API Endpoints

### Sample Scoring

```http
POST /score_sample
```

Score a single training sample. Example request:

```json
{
  "sample_id": "uuid",
  "categorizer_id": "uuid"
}
```

```http
POST /score_batch
```

Score multiple unscored samples. Example request:

```json
{
  "categorizer_id": "uuid",
  "batch_size": 10
}
```

### Curation Management

```http
GET /curation_status/{categorizer_id}
```

Get curation status for a categorizer.

```http
POST /run_curation
```

Manually trigger curation. Example request:

```json
{
  "categorizer_id": "uuid",
  "force": false
}
```

### Health Check

```http
GET /health
```

Returns service health status and background worker state.

## Background Worker

The service includes a background worker that:
- Periodically checks for unscored samples
- Runs quality assessment on batches
- Triggers curation when thresholds are met
- Updates quality metrics

Configuration:
```yaml
quality:
  background_scoring:
    enabled: true
    interval_seconds: 300
    batch_size: 5
```

## Curation Pipeline

The curation process includes:

1. Quality Assessment
   - Scores samples based on multiple metrics
   - Uses text quality, category consistency, etc.

2. Sample Filtering
   - Archives samples below quality threshold
   - Maintains maximum dataset size
   - Preserves highest quality samples

3. Dataset Optimization
   - Balances category distribution
   - Ensures dataset size remains manageable
   - Tracks quality metrics over time

## Configuration

Key configuration parameters:

```yaml
quality:
  curation:
    min_quality_score: 0.1
    dataset_max_size: 800
    trigger_threshold: 50
  background_scoring:
    enabled: true
    interval_seconds: 300
    batch_size: 5
```

## Database Schema

### TrainingSample Extensions
- `quality_score`: Float
- `quality_scored_at`: Timestamp
- `quality_reasoning`: Text
- `quality_metrics`: JSONB
- `is_active`: Boolean
- `archived_at`: Timestamp
- `archive_reason`: String

### CurationRun
- `categorizer_id`: UUID
- `run_at`: Timestamp
- `trigger_reason`: String
- `iteration_number`: Integer
- `total_samples_before`: Integer
- `total_samples_after`: Integer
- `archived_count`: Integer
- `removed_low_quality_count`: Integer
- `avg_quality_before`: Float
- `avg_quality_after`: Float
- `config`: JSONB
- `triggered_reevaluation`: Boolean
- `processing_time_ms`: Integer

## Example Usage

Scoring a sample:

```python
import requests

response = requests.post(
    "http://localhost:8050/score_sample",
    json={
        "sample_id": "sample-uuid",
        "categorizer_id": "categorizer-uuid"
    }
)
print(response.json())
```

Checking curation status:

```python
response = requests.get(
    "http://localhost:8050/curation_status/categorizer-uuid"
)
print(response.json())
```

## Dependencies

- FastAPI
- SQLAlchemy
- PostgreSQL
- Pydantic
- asyncio

## Integration

The Evaluator service integrates with:

- Orchestrator for managing training data
- PostgreSQL for data storage
- Other classification services for model quality feedback
- Background worker for automated quality assessment