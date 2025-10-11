# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import httpx
import json

app = FastAPI(
    title="UCAS LLM Layer",
    version="1.3.0",
    description="LLM classification with fallback category support"
)

OLLAMA_URL = "http://ollama:11434"
DEFAULT_MODEL = "phi3:mini"
gpu_config = {"detected": False, "available": False, "vram_gb": 0}

class GPUConfig(BaseModel):
    num_gpu: Optional[int] = None
    gpu_memory_fraction: Optional[float] = None

class TrainRequest(BaseModel):
    categorizer_id: str
    training_data: List[Dict[str, str]]
    model: str = DEFAULT_MODEL
    gpu_config: Optional[GPUConfig] = None
    fallback_category: Optional[str] = None  # NEW: Out-of-scope category

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str
    model: Optional[str] = None

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    reasoning: str = ""
    method: str = "llm"
    gpu_used: bool = False
    is_fallback: bool = False  # NEW: Indicates out-of-scope

categorizers_config = {}

async def detect_gpu_capabilities():
    global gpu_config
    if gpu_config["detected"]:
        return gpu_config
    try:
        import os
        has_nvidia = os.path.exists("/usr/bin/nvidia-smi") or os.environ.get("CUDA_VISIBLE_DEVICES")
        gpu_config = {"detected": True, "available": bool(has_nvidia), "vram_gb": 8 if has_nvidia else 0}
    except:
        gpu_config = {"detected": True, "available": False, "vram_gb": 0}
    return gpu_config

def calculate_optimal_gpu_layers(model: str, vram_gb: float) -> int:
    model_sizes = {"phi3:mini": 3.8, "gemma:2b": 2.0, "llama3.1:8b": 8.0, "mistral:7b": 7.0}
    params = model_sizes.get(model, 3.8)
    required_vram = params * 2
    if vram_gb >= required_vram:
        return -1
    elif vram_gb >= 4:
        return int(vram_gb / required_vram * 32)
    else:
        return 0

@app.on_event("startup")
async def startup_event():
    gpu_info = await detect_gpu_capabilities()
    print(f"GPU Detection: {gpu_info}")

@app.get("/")
async def root():
    return {
        "service": "UCAS LLM Layer",
        "version": "1.3.0",
        "default_model": DEFAULT_MODEL,
        "features": ["gpu_auto_config", "fallback_category"],
        "gpu_available": gpu_config.get("available", False),
        "categorizers": len(categorizers_config)
    }

@app.get("/health")
async def health_check():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            ollama_status = "connected" if response.status_code == 200 else "error"
    except Exception as e:
        ollama_status = f"disconnected: {str(e)}"
    return {"status": "healthy", "ollama": ollama_status, "gpu": gpu_config, "categorizers": len(categorizers_config)}

async def ensure_model_exists(model: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]
            if model not in model_names:
                pull_request = {"name": model}
                async with client.stream("POST", f"{OLLAMA_URL}/api/pull", json=pull_request, timeout=300.0) as response:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if data.get("status") == "success":
                                return True
                return True
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Ollama error: {str(e)}")

@app.post("/train")
async def train(request: TrainRequest):
    try:
        await ensure_model_exists(request.model)
        categories = list(set([sample["category"] for sample in request.training_data]))
        
        if request.gpu_config and request.gpu_config.num_gpu is not None:
            num_gpu = request.gpu_config.num_gpu
        else:
            gpu_info = await detect_gpu_capabilities()
            num_gpu = calculate_optimal_gpu_layers(request.model, gpu_info["vram_gb"]) if gpu_info["available"] else 0
        
        categorizers_config[request.categorizer_id] = {
            "categories": categories,
            "examples": request.training_data,
            "model": request.model,
            "num_gpu": num_gpu,
            "fallback_category": request.fallback_category  # NEW
        }
        
        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "categories": categories,
            "fallback_category": request.fallback_category,
            "training_samples": len(request.training_data),
            "model": request.model,
            "gpu_config": {"num_gpu": num_gpu, "mode": "GPU" if num_gpu > 0 else "CPU"},
            "method": "few-shot"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    if request.categorizer_id not in categorizers_config:
        return ClassifyResponse(category=None, confidence=0.0, reasoning="Categorizer not found", method="llm")
    
    config = categorizers_config[request.categorizer_id]
    model = request.model or config["model"]
    num_gpu = config.get("num_gpu", 0)
    fallback = config.get("fallback_category")
    
    try:
        prompt = build_classification_prompt(
            request.text, 
            config["categories"], 
            config["examples"][:5],
            fallback
        )
        
        async with httpx.AsyncClient() as client:
            ollama_request = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "top_p": 0.9, "num_gpu": num_gpu}
            }
            
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=ollama_request, timeout=60.0)
            
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail="Ollama failed")
            
            result = response.json()
            llm_response = result["response"].strip()
            category, confidence, reasoning = parse_llm_response(llm_response, config["categories"], fallback)
            
            # Check if result is fallback category
            is_fallback = (category == fallback) if fallback else False
            
            return ClassifyResponse(
                category=category,
                confidence=confidence,
                reasoning=reasoning,
                method="llm",
                gpu_used=(num_gpu > 0),
                is_fallback=is_fallback
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")

def build_classification_prompt(text: str, categories: List[str], examples: List[Dict], fallback_category: Optional[str] = None) -> str:
    """Build prompt with optional fallback category"""
    
    # Add fallback to available categories
    all_categories = categories.copy()
    if fallback_category and fallback_category not in all_categories:
        all_categories.append(fallback_category)
    
    categories_str = ", ".join(all_categories)
    
    examples_text = ""
    for ex in examples:
        examples_text += f"Text: {ex['text']}\nCategory: {ex['category']}\n\n"
    
    # Special instruction for fallback
    fallback_instruction = ""
    if fallback_category:
        main_cats = ", ".join(categories)
        fallback_instruction = f"\n\nIMPORTANT: The main categories are: {main_cats}\nIf the text does NOT clearly fit any of these main categories, classify it as '{fallback_category}'.\nUse '{fallback_category}' for: greetings, thanks, out-of-scope content, or unclear requests."
    
    prompt = f"""You are a text classifier. You MUST classify text into EXACTLY ONE category from this list: {categories_str}

Examples of main categories:
{examples_text}{fallback_instruction}

Now classify this text. Choose EXACTLY ONE category from the list: {categories_str}

Text to classify: {text}

Respond in this EXACT format (no other text):
Category: [write exactly one category from: {categories_str}]
Confidence: [write a number between 0.0 and 1.0]
Reasoning: [write a brief one-sentence explanation]

Your classification:
"""
    return prompt

def parse_llm_response(response: str, valid_categories: List[str], fallback_category: Optional[str] = None) -> tuple:
    """Parse LLM response with fallback support"""
    lines = response.strip().split("\n")
    category = None
    confidence = 0.7
    reasoning = ""
    
    # Add fallback to valid categories
    all_valid = valid_categories.copy()
    if fallback_category and fallback_category not in all_valid:
        all_valid.append(fallback_category)
    
    # Strategy 1: Parse structured format
    for line in lines:
        line = line.strip()
        
        if any(keyword in line for keyword in ["Category:", "Kategoria:", "category:"]):
            cat_text = line.split(":", 1)[-1].strip().strip('."\'')
            
            # Exact match
            for valid_cat in all_valid:
                if cat_text.lower() == valid_cat.lower():
                    category = valid_cat
                    break
            
            # Partial match
            if not category:
                for valid_cat in all_valid:
                    if valid_cat.lower() in cat_text.lower():
                        category = valid_cat
                        break
        
        elif any(keyword in line for keyword in ["Confidence:", "Pewność:", "Pewnosc:", "confidence:"]):
            try:
                conf_text = line.split(":", 1)[-1].strip().replace("%", "").strip()
                confidence = float(conf_text)
                if confidence > 1.0:
                    confidence = confidence / 100.0
            except:
                pass
        
        elif any(keyword in line for keyword in ["Reasoning:", "Uzasadnienie:", "reasoning:"]):
            reasoning = line.split(":", 1)[-1].strip()
    
    # Strategy 2: Search in response
    if not category:
        response_lower = response.lower()
        for valid_cat in all_valid:
            if valid_cat.lower() in response_lower[:300]:
                category = valid_cat
                confidence = 0.6
                break
    
    # Strategy 3: Default to fallback or first category
    if not category:
        if fallback_category:
            category = fallback_category
            confidence = 0.5
            reasoning = "Unable to classify, defaulted to fallback category"
        elif valid_categories:
            category = valid_categories[0]
            confidence = 0.5
            reasoning = "Unable to parse response, defaulted to first category"
    
    return category, confidence, reasoning

@app.get("/categorizers/{categorizer_id}/info")
async def get_info(categorizer_id: str):
    if categorizer_id not in categorizers_config:
        raise HTTPException(status_code=404, detail="Not found")
    config = categorizers_config[categorizer_id]
    return {
        "categorizer_id": categorizer_id,
        "status": "trained",
        "categories": config["categories"],
        "fallback_category": config.get("fallback_category"),
        "training_samples": len(config["examples"]),
        "model": config["model"],
        "gpu_config": {"num_gpu": config.get("num_gpu", 0), "mode": "GPU" if config.get("num_gpu", 0) > 0 else "CPU"}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8030)