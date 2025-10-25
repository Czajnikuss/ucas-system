# XGBoost Layer Service

The XGBoost Layer is a machine learning service that provides text classification capabilities using XGBoost models combined with Word2Vec embeddings. It offers both training and inference endpoints with support for multiple independent categorizers.

## Features

- Training text classifiers with XGBoost and Word2Vec
- Real-time text classification with confidence scores
- Support for multiple categorizers
- Model persistence and caching
- Configurable model parameters
- Health monitoring

## API Endpoints

### Training

```http
POST /train
```

Trains a new categorizer with the specified ID. Example request:

```json
{
  "categorizer_id": "my-classifier",
  "training_data": [
    {"text": "example text", "category": "category-a"},
    {"text": "another example", "category": "category-b"}
  ],
  "params": {
    "max_depth": 6,
    "n_estimators": 100
  },
  "word2vec_params": {
    "vector_size": 100,
    "window": 5,
    "min_count": 1,
    "epochs": 10
  }
}
```

### Classification

```http
POST /classify
```

Classifies text using a trained categorizer. Example request:

```json
{
  "categorizer_id": "my-classifier",
  "text": "text to classify"
}
```

### Model Info

```http
GET /categorizers/{categorizer_id}/info
```

Returns information about a trained categorizer.

### Health Check

```http
GET /health
```

Returns service health status and number of trained models in cache.

## Configuration

### Model Parameters

XGBoost parameters:
- `max_depth`: Maximum tree depth (default: 6)
- `n_estimators`: Number of trees (default: 100)
- `learning_rate`: Learning rate (default: 0.1)
- `subsample`: Subsample ratio (default: 0.8)
- `colsample_bytree`: Column sampling ratio (default: 0.8)

Word2Vec parameters:
- `vector_size`: Embedding dimension (default: 100)
- `window`: Context window size (default: 5)
- `min_count`: Minimum word frequency (default: 1)
- `epochs`: Training epochs (default: 10)

## Data Storage

Models are stored in `/data/models/{categorizer_id}/` with the following structure:
- `xgboost.json`: XGBoost model file
- `word2vec.model`: Word2Vec embeddings
- `label_encoder.pkl`: Category label encoder
- `config.json`: Model configuration and metadata

## Example Usage

Training a new categorizer:

```python
import requests

training_data = [
    {"text": "example of category A", "category": "A"},
    {"text": "example of category B", "category": "B"}
]

response = requests.post(
    "http://localhost:8020/train",
    json={
        "categorizer_id": "test-categorizer",
        "training_data": training_data
    }
)
print(response.json())
```

Classifying text:

```python
response = requests.post(
    "http://localhost:8020/classify",
    json={
        "categorizer_id": "test-categorizer",
        "text": "text to classify"
    }
)
print(response.json())
```

## Dependencies

- FastAPI
- XGBoost
- Gensim (Word2Vec)
- scikit-learn
- NumPy
- Joblib

## Integration

The XGBoost Layer service is typically integrated with:

- Orchestrator service for automated model training and inference
- API Gateway for external access
- Redis for result caching (optional)
- Shared volume for model persistence