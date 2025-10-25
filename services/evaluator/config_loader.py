"""
Configuration loader for UCAS system
Loads config.yaml, config.local.yaml (if exists), and secrets.yaml (if exists)
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    def __init__(self):
        # Config is at /app/config (mounted volume)
        self.config_dir = Path("/app/config")
        self.data = {}
        self._load_all()
    
    def _load_all(self):
        """Load all config files in order"""
        print(f"Loading config from: {self.config_dir}", flush=True)
        
        # 1. Load default config
        default_config = self.config_dir / "config.yaml"
        if default_config.exists():
            with open(default_config, 'r', encoding='utf-8') as f:
                self.data = yaml.safe_load(f) or {}
            print(f"✓ Loaded config.yaml", flush=True)
        else:
            print(f"✗ config.yaml not found at {default_config}", flush=True)
        
        # 2. Load local overrides (if exists)
        local_config = self.config_dir / "config.local.yaml"
        if local_config.exists():
            with open(local_config, 'r', encoding='utf-8') as f:
                local_data = yaml.safe_load(f) or {}
                self._deep_merge(self.data, local_data)
            print(f"✓ Loaded config.local.yaml", flush=True)
        
        # 3. Load secrets (if exists)
        secrets_config = self.config_dir / "secrets.yaml"
        if secrets_config.exists():
            with open(secrets_config, 'r', encoding='utf-8') as f:
                secrets_data = yaml.safe_load(f) or {}
                self._deep_merge(self.data, secrets_data)
            print(f"✓ Loaded secrets.yaml", flush=True)
    
    def _deep_merge(self, base: Dict, override: Dict):
        """Deep merge override into base"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot notation (e.g., 'quality.weights.alignment')"""
        keys = key.split('.')
        value = self.data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value


# Global config instance
config = Config()
