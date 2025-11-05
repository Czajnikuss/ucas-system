# Orchestrator Service

The orchestrator is the central component of the UCAS system. It is responsible for:

* **Training**: Creating and training new categorizers.
* **Classification**: Classifying text using the cascade architecture.
* **Management**: Managing categorizers and viewing metadata.
* **Analytics**: Providing classification history and performance metrics.
* **RAG**: Handling retrieval-augmented generation and similarity search.

## File Structure

The orchestrator service is organized into the following files:

* **`main.py`**: Initializes the FastAPI app and includes the routers for the different modules.
* **`api/`**: This directory contains the API endpoints, organized by functionality.
    * **`__init__.py`**: Makes the `api` directory a Python package.
    * **`training.py`**: Contains the `/train` endpoint for creating and training new categorizers.
    * **`classification.py`**: Contains the `/classify` endpoint and the different classification strategies.
    * **`management.py`**: Contains the endpoints for managing categorizers (listing, getting details, and deleting).
    * **`analytics.py`**: Contains the endpoints for analytics (history, training samples, and cascade stats).
    * **`rag.py`**: Contains the RAG-related endpoints (similarity search and stats).
* **`persistence.py`**: Handles the persistence of categorizer models to disk.
* **`models/`**: Contains the database models.
    * **`database.py`**: Defines the database schema and provides session management.
* **`config_loader.py`**: Loads the configuration from `config.yaml` and `secrets.yaml`.
