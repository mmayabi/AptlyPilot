# AptlyPilot Development Guide

## Requirements

- Python 3.12
- Docker
- Docker Compose

## Run with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

## API Docs
```
http://localhost:8000/docs
```

## Health Check
```
curl http://localhost:8000/api/v1/health
```

## Run Tests
```
docker compose exec api pytest
```