# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import httpx
import json
import sys
import re

app = FastAPI(
    title="UCAS LLM Layer",
    version="1.3.1",
    description="LLM classification with rich logging and strict error handling"
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
    fallback_category: Optional[str] = None

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
    is_fallback: bool = False
    prompt_used: Optional[str] = None  # 🎯 KLUCZOWE: Dodano pole na prompt

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
    print(f"✅ LLM Layer started. GPU Detection: {gpu_info}", flush=True)

@app.get("/")
async def root():
    return {"service": "UCAS LLM Layer", "version": "1.3.1"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "gpu": gpu_config, "categorizers_in_memory": len(categorizers_config)}

async def ensure_model_exists(model: str):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{OLLAMA_URL}/api/tags", timeout=10.0)
            models = response.json().get("models", [])
            model_names = [m["name"] for m in models]
            if model not in model_names:
                print(f"⏳ Pulling model {model} from Ollama...", flush=True)
                pull_request = {"name": model}
                async with client.stream("POST", f"{OLLAMA_URL}/api/pull", json=pull_request, timeout=300.0) as response:
                    async for line in response.aiter_lines():
                        if line:
                            data = json.loads(line)
                            if data.get("status") == "success":
                                return True
            return True
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Ollama connection error: {str(e)}")

@app.post("/train")
async def train(request: TrainRequest):
    print(f"📥 Received TRAINING request for: {request.categorizer_id} with {len(request.training_data)} samples.", flush=True)
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
            "fallback_category": request.fallback_category
        }
        print(f"✅ Successfully seeded memory for {request.categorizer_id}.", flush=True)
        
        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "categories": categories,
            "training_samples": len(request.training_data),
            "model": request.model,
            "method": "few-shot"
        }
    except Exception as e:
        print(f"🔴 Error during train: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    print(f"🔍 CLASSIFY REQUEST | Categorizer: {request.categorizer_id} | Text: '{request.text[:50]}...'", flush=True)
    
    if request.categorizer_id not in categorizers_config:
        print(f"🔴 ERROR: Categorizer '{request.categorizer_id}' NOT FOUND in RAM.", flush=True)
        raise HTTPException(status_code=404, detail="Categorizer not found in LLM memory. Has it been trained/restored?")
    
    config = categorizers_config[request.categorizer_id]
    model = request.model or config["model"]
    num_gpu = config.get("num_gpu", 0)
    fallback = config.get("fallback_category")
    
    examples_to_use = config["examples"][:5]
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as rag_client:
            print(f"   📡 Fetching RAG context...", flush=True)
            rag_response = await rag_client.post(
                "http://rag-service:8070/search",
                json={"categorizer_id": request.categorizer_id, "query_text": request.text, "top_k": 5}
            )
            if rag_response.status_code == 200:
                rag_data = rag_response.json()
                rag_examples = [{"text": s["text"], "category": s["category"]} for s in rag_data["samples"]]
                if rag_examples:
                    examples_to_use = rag_examples
                    print(f"   ✅ RAG returned {len(examples_to_use)} samples.", flush=True)
            else:
                print(f"   ⚠️ RAG returned {rag_response.status_code}. Using static fallback.", flush=True)
    except Exception as e:
        print(f"   ⚠️ RAG connection failed: {e}. Using static fallback.", flush=True)
    
    try:
        prompt = build_classification_prompt(request.text, config["categories"], examples_to_use, fallback)
        print(f"   🧠 Sending prompt to Ollama model '{model}'...", flush=True)
        
        async with httpx.AsyncClient() as client:
            ollama_request = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",  # wymuszamy poprawny JSON na wyjsciu (koniec kruchego parsowania)
                "options": {"temperature": 0.1, "top_p": 0.9, "num_gpu": num_gpu}
            }
            
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=ollama_request, timeout=60.0)
            
            if response.status_code != 200:
                print(f"🔴 Ollama Error: {response.text}", flush=True)
                raise HTTPException(status_code=response.status_code, detail="Ollama generation failed")
            
            result = response.json()
            llm_response = result["response"].strip()
            print(f"   💬 Raw Ollama Output:\n--- START ---\n{llm_response}\n--- END ---", flush=True)
            
            category, confidence, reasoning = parse_llm_response(llm_response, config["categories"], fallback)
            is_fallback = (category == fallback) if fallback else False
            
            print(f"   🎯 Final parsing -> Cat: {category}, Conf: {confidence}", flush=True)
            return ClassifyResponse(
                category=category,
                confidence=confidence,
                reasoning=reasoning,
                method="llm",
                gpu_used=(num_gpu > 0),
                is_fallback=is_fallback,
                prompt_used=prompt  # 🎯 KLUCZOWE: Zwrot promptu do Orchestratora
            )
    except Exception as e:
        print(f"🔴 Classification execution failed: {e}", flush=True)
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")

def build_classification_prompt(text: str, categories: List[str], examples: List[Dict], fallback_category: Optional[str] = None) -> str:
    all_categories = categories.copy()
    if fallback_category and fallback_category not in all_categories:
        all_categories.append(fallback_category)
    
    categories_str = ", ".join(all_categories)
    examples_text = "".join([f'- "{ex["text"]}" => {ex["category"]}\n' for ex in examples])

    fallback_instruction = ""
    if fallback_category:
        fallback_instruction = (
            f'\nUWAGA: jeśli tekst NIE jest zgłoszeniem pasującym do żadnej z głównych kategorii '
            f'(np. podziękowanie, pozytywna opinia, tekst nie na temat), przypisz kategorię '
            f'"{fallback_category}" i nadaj NISKĄ pewność (≤ 0.4).'
        )

    return f"""Jesteś klasyfikatorem zgłoszeń systemowych. Przypisz tekst do DOKŁADNIE JEDNEJ kategorii z listy:
{categories_str}
{fallback_instruction}

Przykłady referencyjne (tekst => kategoria):
{examples_text}
Tekst do sklasyfikowania:
"{text}"

Zwróć WYŁĄCZNIE obiekt JSON, bez żadnego dodatkowego tekstu, w formacie:
{{"category": "<dokładnie jedna kategoria z listy>", "confidence": <liczba 0.0-1.0>, "reasoning": "<krótkie uzasadnienie po polsku>"}}"""

def parse_llm_response(response: str, valid_categories: List[str], fallback_category: Optional[str] = None) -> tuple:
    category = None
    confidence = 0.7
    reasoning = ""

    all_valid = valid_categories.copy()
    if fallback_category and fallback_category not in all_valid:
        all_valid.append(fallback_category)

    def _match_category(raw: str):
        raw = (raw or "").strip()
        for valid_cat in all_valid:
            if valid_cat.lower() in raw.lower() or raw.lower() in valid_cat.lower():
                return valid_cat
        return None

    # 1. Sciezka glowna: model jest proszony o JSON (Ollama format=json).
    parsed = None
    try:
        parsed = json.loads(response)
    except Exception:
        m = re.search(r"\{.*\}", response, re.DOTALL)  # czasem model owinie JSON tekstem
        if m:
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                parsed = None

    if isinstance(parsed, dict):
        category = _match_category(str(parsed.get("category", "")))
        try:
            confidence = float(parsed.get("confidence", 0.7))
            if confidence > 1.0:
                confidence /= 100.0
        except Exception:
            confidence = 0.7
        reasoning = str(parsed.get("reasoning", "")).strip()
    else:
        # 2. Fallback: stare parsowanie liniowe (gdyby format JSON zawiodl)
        for line in response.strip().split("\n"):
            line = line.strip()
            if any(k in line.lower() for k in ["category:", "kategoria:"]):
                if not category:
                    category = _match_category(line.split(":", 1)[-1].strip().strip('."\''))
            elif any(k in line.lower() for k in ["confidence:", "pewnosc:", "pewność:"]):
                try:
                    conf_text = line.split(":", 1)[-1].strip().replace("%", "").strip()
                    confidence = float(conf_text)
                    if confidence > 1.0: confidence /= 100.0
                except: pass
            elif any(k in line.lower() for k in ["reasoning:", "uzasadnienie:"]):
                reasoning = line.split(":", 1)[-1].strip()

    if not category:
        if fallback_category:
            return fallback_category, 0.5, "Defaulted to fallback"
        elif valid_categories:
            return valid_categories[0], 0.5, "Failed to parse, defaulted to first"
            
    return category, confidence, reasoning

@app.get("/categorizers/{categorizer_id}/info")
async def get_info(categorizer_id: str):
    if categorizer_id not in categorizers_config:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "trained", "categories": categorizers_config[categorizer_id]["categories"]}