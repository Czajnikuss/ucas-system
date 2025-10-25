# UCAS — Universal Classification & Analysis System

> Production-ready, multi-layer text classification system. Combines fast rules, XGBoost and an LLM reasoning layer.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Table of Contents
- [Project Purpose](#project-purpose)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Contributing](#contributing)
- [License](#license)
- [Notes](#notes)

## Project Purpose
The UCAS project provides a robust and efficient system for text classification and analysis. It integrates multiple classification layers in a cascade approach:

1. **[Tags Layer](services/tags-layer/README.md)** - Fast, rule-based classification for exact and partial matches
   - Polish language optimization
   - TF-IDF and discriminative analysis
   - Fast pattern matching

2. **[XGBoost Layer](services/xgboost-layer/README.md)** - Machine learning classification using word embeddings
   - Word2Vec embeddings
   - XGBoost classifier
   - Automatic evaluation

3. **[LLM Layer](services/llm-layer/README.md)** - Advanced reasoning using large language models
   - Few-shot learning
   - RAG with dynamic examples
   - GPU support

4. **[HIL Layer](services/hil-layer/README.md)** - Human-in-the-loop for uncertain cases
   - Case queueing
   - Reviewer interface
   - Continuous learning

### Architektura Systemu

System składa się z następujących komponentów:
- **[API Gateway](services/api-gateway/README.md)** - Główny punkt wejścia, routing i autoryzacja
- **[Orchestrator](services/orchestrator/README.md)** - Zarządzanie przepływem i koordynacja
- **[Evaluator](services/evaluator/README.md)** - Metryki i monitoring jakości
- Warstwy klasyfikacji (wymienione powyżej)
- Bazy danych:
  - PostgreSQL (dane treningowe, historia)
  - Redis (cache, rate limiting)
  - Ollama (modele LLM)

### Key Features
- 🚀 Multi-layer cascade classification
- 📊 Real-time performance monitoring
- 🔄 Continuous learning from user feedback
- 🤝 Human-in-the-loop integration
- 📈 Automated model evaluation
- 🔍 Detailed classification explanations

### API Documentation
- Swagger UI: http://localhost:8001/swagger
- ReDoc: http://localhost:8001/redoc
- API Status: http://localhost:8001/health

## Project Structure
```
.
├── docker-compose.yml
├── README.md
├── config/
├── logs/
├── scripts/
├── services/
│   ├── api-gateway/
│   ├── evaluator/
│   ├── hil-layer/
│   ├── llm-layer/
│   ├── orchestrator/
│   ├── postgres/
│   ├── redis/
│   ├── tags-layer/
│   └── xgboost-layer/
├── test_data/
├── volumes/
└── models/
```

## Installation

### Prerequisites
- Docker Engine 24.0+
- Docker Compose v2.0+
- 8GB RAM minimum (16GB recommended)
- 20GB free disk space

### Quick Start
1. Clone the repository:
```bash
git clone https://github.com/Czajnikuss/ucas-system.git
cd ucas-system
```

2. Build and start the services:
```bash
docker-compose up --build
```

3. Verify installation:
```bash
./test.ps1
```

### Configuration
Key configuration files:
- `config/default.json` - General system settings
- `services/*/config.json` - Service-specific settings
- `.env` - Environment variables (create from `.env.example`)

## Usage

### Starting the System
```bash
docker-compose up -d
```

### API Examples
1. Create a new categorizer:
```bash
curl -X POST http://localhost:8001/train \
  -H "Content-Type: application/json" \
  -d @test_data/train_cascade.json
```

2. Classify text:
```bash
curl -X POST http://localhost:8001/classify \
  -H "Content-Type: application/json" \
  -d '{
    "categorizer_id": "your-categorizer-id",
    "text": "Text to classify",
    "strategy": "cascade"
  }'
```

### Monitoring
- System Health: http://localhost:8001/health
- Metrics Dashboard: http://localhost:8001/metrics
- Classification History: http://localhost:8001/history

## Contributing
Contributions are welcome! Please read the [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Service Architecture

### API Gateway (Port 8001)
- Main entry point for all requests
- Request validation and routing
- Rate limiting and authentication
- Swagger documentation

### Orchestrator
- Classification workflow management
- Result aggregation and scoring
- Service health monitoring
- Database interactions

### Classification Layers
1. **Tags Layer**
   - Rule-based classification
   - Fast exact and partial matching
   - Regular expression support
   
2. **XGBoost Layer**
   - Word2Vec embeddings
   - XGBoost classifier
   - Confidence scoring
   
3. **LLM Layer**
   - Large Language Model reasoning
   - Context-aware classification
   - Explanation generation
   
4. **HIL Layer**
   - Human review interface
   - Feedback collection
   - Training data curation

### Persistence
- PostgreSQL: Classification data and metrics
- Redis: Caching and rate limiting
- Volume mounts: Model storage and configs

## Troubleshooting

### Common Issues
1. **Database Connection Issues**
   ```bash
   docker-compose down -v  # Clear volumes
   docker-compose up -d    # Fresh start
   ```

2. **Model Loading Errors**
   ```bash
   docker-compose restart xgboost-layer llm-layer
   ```

3. **Permission Issues**
   - Check volume permissions
   - Verify database user setup
   - Review service logs

### Getting Help
- Check service logs: `docker-compose logs [service]`
- Review Swagger docs: http://localhost:8001/docs
- Open an issue on GitHub
- Run e2e tests: `./test.ps1`
