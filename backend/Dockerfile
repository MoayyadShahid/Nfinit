FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libgl1 \
        libglib2.0-0 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==2.1.1

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-interaction --no-ansi --only main

# PYTHONDONTWRITEBYTECODE stops runtime .pyc writes, so precompile once here.
# Otherwise every sandbox worker recompiles build123d, which roughly doubles
# the CPU cost of each CAD run.
RUN python -m compileall -q -j 0 "$(python -c 'import site; print(site.getsitepackages()[0])')"

COPY . .

EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
