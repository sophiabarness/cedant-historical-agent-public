# Trusting AI Agents: A Reinsurance Industry Case Study

This repository contains code for an AI assistant which helps underwriters convert messy Excel submission pack data into clean, structured catastrophe records. It parses excel submission packs, links to historical data, and produces a clean, final output. It features a multi-agent design with human-in-the-loop. 

See demo video: https://youtu.be/NkQ8bA3AcAQ?si=Mbz7bhkbJX3Go6A2

![Agent Architecture](./docs/agent-architecture.png)
![Full App Architecture](./docs/implementation-HITL.png)

## Navigating the Codebase

| Directory   | Description                                                        |
|-------------|--------------------------------------------------------------------|
| `frontend`  | React-based UI for interacting with the agent                      |
| `api`       | FastAPI server that interfaces between the UI and Temporal workflows |
| `agents`    | Core agent logic, prompts, and supervisor workflow definitions     |
| `worker`    | Temporal worker that executes workflows and activities             |
| `shared`    | Shared configuration and bridge workflow utilities                 |
| `models`    | Pydantic models for requests and data structures                   |
| `data`      | data files (cedant loss data, historical events, submission packs)  |

## Running the Application

### Prerequisites

- Python 3.10+
- Node.js (for frontend)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- Access to Temporal (local or cloud)
- LLM API key (OpenAI or AWS Bedrock)

### 1. Configure Environment

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

Key variables to set:
- `LLM_MODEL` / `LLM_MODEL_FAST` - Your LLM model identifiers
- `LLM_KEY` - Your API key
- `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY` - Temporal connection details

### 2. Start the Temporal Service

For local development:
```bash
temporal server start-dev
```

For Temporal Cloud, ensure your `.env` has the correct `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, and `TEMPORAL_API_KEY`.

### 3. Run the Worker

```bash
uv run python -m worker.worker
```

### 4. Run the API

```bash
uv run uvicorn api.main:app --reload --port 8000
```

### 5. Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:5173`.

## License

This project is open source and available under the MIT License.
