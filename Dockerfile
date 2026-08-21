FROM python:3.12.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir --upgrade pip

COPY backend/pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -e ".[dev]" 

COPY backend/app /app/app
COPY backend/tests /app/tests
COPY backend/scripts /app/scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
