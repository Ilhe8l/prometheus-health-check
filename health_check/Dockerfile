FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock* ./

RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root \
    && poetry cache clear --all pypi

COPY . /app/

RUN mkdir -p /app/logs

# Adicione o usuário ao grupo docker (se necessário)
RUN groupadd -g 999 docker || true

EXPOSE 8000 9090

CMD ["python", "health_exporter.py"]