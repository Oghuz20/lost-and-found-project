# Smart Lost & Found

A service that matches lost items against found items using a vision-language description plus embedding similarity. The `ai/` package (VLM + embedding + similarity) is provided; everything else — storage, HTTP API, CLI, concurrency, retries, validation, logging, telemetry, Docker — is built by the team.

## Architecture in one diagram
![Architecture Diagram](artefacts/lost_and_found_final_architecture.png)

## Setup & Installation

```bash
# 1. Clone and enter the repo
git clone <your-repo-url> && cd <your-repo>

# 2. Create and activate a virtualenv
python3 -m venv .venv && source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt -r requirements-ai.txt

# 4. Copy environment template
cp .env.example .env

# 5. Run smoke tests
python demo_ai.py --offline
pytest tests/test_ai_smoke.py -v