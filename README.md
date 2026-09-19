# Smart Lost & Found System - Core Module

## Features Implemented
- **FastAPI Endpoints**: `/items/lost`, `/items/found`, and `/items/{id}/matches` with Pydantic schema validation.
- **VLM Pipeline**: Integration with Gemini VLM for multimodal image analysis and vector embedding generation.
- **Concurrency & Rate Limiting**: Asynchronous batch processing and token-bucket rate limiter for API quota management.
- **Telemetry**: Cost tracker module for real-time monitoring of token consumption.

## Directory Structure
- `src/`: Core application logic, API endpoints, services, storage, and telemetry.
- `scripts/`: Execution and benchmarking scripts (`demo.py`, `bench.py`).
- `tests/`: Automated unit and integration test suites.
