# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import xgboost as xgb
from gensim.models import Word2Vec
import numpy as np
import joblib
import json
from pathlib import Path
from cachetools import TTLCache
from vectorizer import text_to_regional_vector, VectorizationConfig
import re
import unicodedata

app = FastAPI(
    title="UCAS XGBoost Layer",
    version="1.2.0",
    description="ML text classification. Cechy: pretrenowane embeddingi (transfer learning) lub Word2Vec (fallback)."
)

MODELS_DIR = Path("/data/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
models_cache = TTLCache(maxsize=10, ttl=3600)

class TrainRequest(BaseModel):
    categorizer_id: str
    training_data: List[Dict[str, str]]
    # Pretrenowane embeddingi (z embeddings-service), wyrownane do training_data.
    # Gdy podane -> tryb "embeddings" (transfer learning). Gdy brak -> fallback Word2Vec.
    embeddings: Optional[List[List[float]]] = None
    params: Optional[Dict] = {"max_depth": 6, "n_estimators": 100}
    word2vec_params: Optional[Dict] = {"vector_size": 100, "window": 5, "min_count": 1, "epochs": 10}

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str
    # Embedding zapytania (z embeddings-service). Wymagany gdy model jest w trybie "embeddings".
    embedding: Optional[List[float]] = None

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    probabilities: Dict[str, float] = {}
    method: str = "xgboost"

@app.get("/")
async def root():
    return {"service": "UCAS XGBoost Layer", "status": "running", "version": "1.2.0", "trained_models": len(models_cache)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "trained_models": len(models_cache)}

def normalize_text(text: str) -> str:
    """Usuwa diakrytyki (NFD) i zamienia na male litery (dla sciezki Word2Vec)."""
    if not text:
        return ""
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.lower()

def tokenize(text: str) -> list:
    text = normalize_text(text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.split()

def _build_xgb(num_params: Dict):
    return xgb.XGBClassifier(
        max_depth=num_params.get("max_depth", 6),
        n_estimators=num_params.get("n_estimators", 100),
        learning_rate=num_params.get("learning_rate", 0.1),
        subsample=num_params.get("subsample", 0.8),
        colsample_bytree=num_params.get("colsample_bytree", 0.8),
        objective='multi:softprob',
        eval_metric='mlogloss',
        use_label_encoder=False
    )

def get_model(categorizer_id: str):
    if categorizer_id in models_cache:
        return models_cache[categorizer_id]

    model_path = MODELS_DIR / categorizer_id
    if not model_path.exists():
        raise ValueError("Model not found")

    with open(model_path / "config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(str(model_path / "xgboost.json"))
    label_encoder = joblib.load(str(model_path / "label_encoder.pkl"))

    # Word2Vec wczytujemy tylko gdy model faktycznie go uzywa (tryb fallback).
    word2vec_model = None
    if config.get("feature_mode", "word2vec") == "word2vec":
        word2vec_model = Word2Vec.load(str(model_path / "word2vec.model"))

    models_cache[categorizer_id] = (xgb_model, word2vec_model, label_encoder, config)
    return models_cache[categorizer_id]

@app.post("/train")
async def train(request: TrainRequest):
    try:
        texts = [sample["text"] for sample in request.training_data]
        categories = [sample["category"] for sample in request.training_data]

        if len(texts) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 samples")

        use_embeddings = bool(request.embeddings) and len(request.embeddings) == len(texts)
        word2vec_model = None

        if use_embeddings:
            # Transfer learning: cechy z pretrenowanego enkodera (semantyczne, wielojezyczne).
            feature_mode = "embeddings"
            X = np.asarray(request.embeddings, dtype=np.float32)
        else:
            # Fallback: Word2Vec uczony od zera na tym kategoryzatorze (slabszy na malych zbiorach).
            feature_mode = "word2vec"
            tokenized_texts = [tokenize(t) for t in texts]
            w2v_params = request.word2vec_params or {}
            word2vec_model = Word2Vec(
                sentences=tokenized_texts,
                vector_size=w2v_params.get("vector_size", 100),
                window=w2v_params.get("window", 5),
                min_count=w2v_params.get("min_count", 1),
                workers=w2v_params.get("workers", 4),
                epochs=w2v_params.get("epochs", 10)
            )
            vector_config = VectorizationConfig(vector_size=word2vec_model.vector_size)
            X = np.array([text_to_regional_vector(tok, word2vec_model, vector_config) for tok in tokenized_texts])

        from sklearn.preprocessing import LabelEncoder
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(categories)

        xgb_model = _build_xgb(request.params or {})
        xgb_model.fit(X, y)

        from sklearn.metrics import accuracy_score
        accuracy = accuracy_score(y, xgb_model.predict(X))

        model_path = MODELS_DIR / request.categorizer_id
        model_path.mkdir(parents=True, exist_ok=True)
        xgb_model.save_model(str(model_path / "xgboost.json"))
        joblib.dump(label_encoder, str(model_path / "label_encoder.pkl"))
        if word2vec_model is not None:
            word2vec_model.save(str(model_path / "word2vec.model"))

        config_data = {
            "feature_mode": feature_mode,
            "categories": label_encoder.classes_.tolist(),
            "training_samples": len(texts),
            "vector_size": int(X.shape[1]),
            "params": request.params or {}
        }
        with open(model_path / "config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)

        models_cache[request.categorizer_id] = (xgb_model, word2vec_model, label_encoder, config_data)

        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "feature_mode": feature_mode,
            "categories": config_data["categories"],
            "training_samples": len(texts),
            "training_accuracy": float(accuracy),
            "dimensions_used": int(X.shape[1]),
            "model_path": str(model_path)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    try:
        xgb_model, word2vec_model, label_encoder, config = get_model(request.categorizer_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Model not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load: {str(e)}")

    try:
        if config.get("feature_mode", "word2vec") == "embeddings":
            if not request.embedding:
                raise HTTPException(status_code=400, detail="Embedding required for embeddings-mode model")
            X = np.asarray(request.embedding, dtype=np.float32).reshape(1, -1)
        else:
            vector_config = VectorizationConfig(vector_size=word2vec_model.vector_size)
            tokens = tokenize(request.text)
            X = text_to_regional_vector(tokens, word2vec_model, vector_config).reshape(1, -1)

        probabilities = xgb_model.predict_proba(X)[0]
        predicted_idx = int(np.argmax(probabilities))
        category = label_encoder.inverse_transform([predicted_idx])[0]
        confidence = float(probabilities[predicted_idx])
        all_probs = {label_encoder.inverse_transform([i])[0]: float(p) for i, p in enumerate(probabilities)}

        return ClassifyResponse(category=category, confidence=confidence, probabilities=all_probs, method="xgboost")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")

@app.get("/categorizers/{categorizer_id}/info")
async def get_model_info(categorizer_id: str):
    model_path = MODELS_DIR / categorizer_id
    if not model_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")
    try:
        with open(model_path / "config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
        return {"categorizer_id": categorizer_id, "status": "trained", "config": config, "cached": categorizer_id in models_cache}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
