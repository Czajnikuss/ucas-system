import json
import pickle
from pathlib import Path
from typing import Dict, Any, Optional

PERSIST_DIR = Path("/data/categorizers")
PERSIST_DIR.mkdir(parents=True, exist_ok=True)

def get_categorizer_dir(categorizer_id: str) -> Path:
    """Get categorizer directory, create if needed"""
    cat_dir = PERSIST_DIR / categorizer_id / "layers"
    cat_dir.mkdir(parents=True, exist_ok=True)
    return cat_dir

def save_layer_state(categorizer_id: str, layer: str, data: Any):
    """Save layer state to disk"""
    cat_dir = get_categorizer_dir(categorizer_id)
    
    if layer == "tags":
        file_path = cat_dir / "tags.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    elif layer == "xgboost":
        # Save model
        model_path = cat_dir / "xgboost_model.pkl"
        with open(model_path, 'wb') as f:
            pickle.dump(data.get("model"), f)
        
        # Save vectorizer
        vec_path = cat_dir / "xgboost_vectorizer.pkl"
        with open(vec_path, 'wb') as f:
            pickle.dump(data.get("vectorizer"), f)
    
    elif layer == "llm":
        file_path = cat_dir / "llm_config.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Saved {layer} state for {categorizer_id}", flush=True)

def load_layer_state(categorizer_id: str, layer: str) -> Optional[Any]:
    """Load layer state from disk"""
    cat_dir = get_categorizer_dir(categorizer_id)
    
    try:
        if layer == "tags":
            file_path = cat_dir / "tags.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        
        elif layer == "xgboost":
            model_path = cat_dir / "xgboost_model.pkl"
            vec_path = cat_dir / "xgboost_vectorizer.pkl"
            
            if model_path.exists() and vec_path.exists():
                with open(model_path, 'rb') as f:
                    model = pickle.load(f)
                with open(vec_path, 'rb') as f:
                    vectorizer = pickle.load(f)
                return {"model": model, "vectorizer": vectorizer}
        
        elif layer == "llm":
            file_path = cat_dir / "llm_config.json"
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
    
    except Exception as e:
        print(f"Failed to load {layer} state: {e}", flush=True)
    
    return None

def categorizer_has_persisted_state(categorizer_id: str) -> bool:
    """Check if categorizer has any persisted files"""
    cat_dir = PERSIST_DIR / categorizer_id / "layers"
    return cat_dir.exists() and any(cat_dir.iterdir())
