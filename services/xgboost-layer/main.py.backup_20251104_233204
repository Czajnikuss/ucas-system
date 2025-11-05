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

app = FastAPI(
    title="UCAS XGBoost Layer",
    version="1.0.0",
    description="ML-based text classification with Word2Vec embeddings"
)

MODELS_DIR = Path("/data/models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)
models_cache = {}

class TrainRequest(BaseModel):
    categorizer_id: str
    training_data: List[Dict[str, str]]
    params: Optional[Dict] = {"max_depth": 6, "n_estimators": 100}
    word2vec_params: Optional[Dict] = {"vector_size": 100, "window": 5, "min_count": 1, "epochs": 10}

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    probabilities: Dict[str, float] = {}
    method: str = "xgboost"

@app.get("/")
async def root():
    return {"service": "UCAS XGBoost Layer", "status": "running", "version": "1.0.0", "trained_models": len(models_cache)}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "trained_models": len(models_cache)}

def tokenize(text: str) -> List[str]:
    import re
    words = re.findall(r'\b[\w]+\b', text.lower(), re.UNICODE)
    return [w for w in words if len(w) >= 2]

def text_to_vector(text: str, word2vec_model: Word2Vec) -> np.ndarray:
    tokens = tokenize(text)
    vectors = [word2vec_model.wv[token] for token in tokens if token in word2vec_model.wv]
    if not vectors:
        return np.zeros(word2vec_model.vector_size)
    return np.mean(vectors, axis=0)

@app.post("/train")
async def train(request: TrainRequest):
    try:
        texts = [sample["text"] for sample in request.training_data]
        categories = [sample["category"] for sample in request.training_data]
        
        if len(texts) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 samples")
        
        tokenized_texts = [tokenize(text) for text in texts]
        w2v_params = request.word2vec_params or {}
        word2vec_model = Word2Vec(
            sentences=tokenized_texts,
            vector_size=w2v_params.get("vector_size", 100),
            window=w2v_params.get("window", 5),
            min_count=w2v_params.get("min_count", 1),
            workers=w2v_params.get("workers", 4),
            epochs=w2v_params.get("epochs", 10)
        )
        
        X = np.array([text_to_vector(text, word2vec_model) for text in texts])
        
        from sklearn.preprocessing import LabelEncoder
        label_encoder = LabelEncoder()
        y = label_encoder.fit_transform(categories)
        
        xgb_params = request.params or {}
        xgb_model = xgb.XGBClassifier(
            max_depth=xgb_params.get("max_depth", 6),
            n_estimators=xgb_params.get("n_estimators", 100),
            learning_rate=xgb_params.get("learning_rate", 0.1),
            subsample=xgb_params.get("subsample", 0.8),
            colsample_bytree=xgb_params.get("colsample_bytree", 0.8),
            objective='multi:softprob',
            eval_metric='mlogloss',
            use_label_encoder=False
        )
        
        xgb_model.fit(X, y)
        train_predictions = xgb_model.predict(X)
        from sklearn.metrics import accuracy_score
        accuracy = accuracy_score(y, train_predictions)
        
        model_path = MODELS_DIR / request.categorizer_id
        model_path.mkdir(exist_ok=True)
        xgb_model.save_model(str(model_path / "xgboost.json"))
        word2vec_model.save(str(model_path / "word2vec.model"))
        joblib.dump(label_encoder, str(model_path / "label_encoder.pkl"))
        
        config = {
            "categories": label_encoder.classes_.tolist(),
            "training_samples": len(texts),
            "vector_size": word2vec_model.vector_size,
            "vocab_size": len(word2vec_model.wv),
            "params": xgb_params
        }
        
        with open(model_path / "config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        models_cache[request.categorizer_id] = (xgb_model, word2vec_model, label_encoder, config)
        
        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "categories": config["categories"],
            "training_samples": len(texts),
            "training_accuracy": float(accuracy),
            "vector_size": word2vec_model.vector_size,
            "vocabulary_size": len(word2vec_model.wv),
            "model_path": str(model_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    if request.categorizer_id not in models_cache:
        model_path = MODELS_DIR / request.categorizer_id
        if not model_path.exists():
            return ClassifyResponse(category=None, confidence=0.0, method="xgboost")
        
        try:
            xgb_model = xgb.XGBClassifier()
            xgb_model.load_model(str(model_path / "xgboost.json"))
            word2vec_model = Word2Vec.load(str(model_path / "word2vec.model"))
            label_encoder = joblib.load(str(model_path / "label_encoder.pkl"))
            with open(model_path / "config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
            models_cache[request.categorizer_id] = (xgb_model, word2vec_model, label_encoder, config)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load: {str(e)}")
    
    xgb_model, word2vec_model, label_encoder, config = models_cache[request.categorizer_id]
    
    try:
        text_vector = text_to_vector(request.text, word2vec_model)
        X = text_vector.reshape(1, -1)
        probabilities = xgb_model.predict_proba(X)[0]
        predicted_idx = np.argmax(probabilities)
        category = label_encoder.inverse_transform([predicted_idx])[0]
        confidence = float(probabilities[predicted_idx])
        all_probs = {label_encoder.inverse_transform([i])[0]: float(p) for i, p in enumerate(probabilities)}
        return ClassifyResponse(category=category, confidence=confidence, probabilities=all_probs, method="xgboost")
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
    uvicorn.run(app, host="0.0.0.0", port=8020)