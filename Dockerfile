FROM python:3.12.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN export http_proxy="http://172.20.8.33:20171" && \
    export https_proxy="http://172.20.8.33:20171" && \
    pip install --no-cache-dir --upgrade pip && \
    export http_proxy="" && export https_proxy=""

COPY backend/pyproject.toml /app/pyproject.toml

RUN export http_proxy="http://172.20.8.33:20171" && \
    export https_proxy="http://172.20.8.33:20171" && \
    pip install --no-cache-dir -e ".[dev]" && \
    export http_proxy="" && export https_proxy=""

COPY backend/app /app/app
COPY backend/tests /app/tests
COPY backend/scripts /app/scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]