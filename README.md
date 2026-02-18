# Nfinit

AI-native CAD IDE for comparing how different LLMs handle 3D geometry code.

## Setup

### Backend (FastAPI)

```bash
cd backend
poetry install
poetry run uvicorn main:app --reload --port 8000
```

Optional: copy `.env.example` to `.env` and adjust CORS origins if needed.

**Note:** build123d requires OCP (OpenCASCADE) and VTK. If `poetry install` fails (e.g. VTK wheel not found), use conda:

```bash
# Create conda env with OpenCASCADE
conda create -n nfinit python=3.11
conda activate nfinit
conda install -c conda-forge pythonocc-core

# Use conda's Python for Poetry (from Nfinit project root)
cd backend
poetry install
poetry run uvicorn main:app --reload --port 8000
```

### Frontend (Next.js)

```bash
cd frontend
cp .env.local.example .env.local  # or create .env.local
# Add your OPENROUTER_API_KEY to .env.local
npm install
npm run dev
```

### Environment

**Frontend:** Copy `frontend/.env.local.example` to `frontend/.env.local`:

```
OPENROUTER_API_KEY=sk-or-v1-your-key-here
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

**Backend:** Optional. Copy `backend/.env.example` to `backend/.env` to customize CORS origins.

## Usage

1. Start the backend on port 8000
2. Start the frontend on port 3000
3. Open http://localhost:3000
4. Select a model (DeepSeek V3.2, Claude Opus 4.6, or Minimax 2.5)
5. Type a prompt (e.g. "a 10mm cube with a 3mm hole through the center")
6. Press Generate or Cmd+Enter

The AI generates build123d Python code, which is executed by the backend to produce a GLB mesh displayed in the 3D viewport.
