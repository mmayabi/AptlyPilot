# AptlyPilot

AptlyPilot is a standalone FastAPI-based control plane for managing aptly mirrors, snapshots, publishes, jobs, and repository automation.

## Goals

AptlyPilot aims to provide:

- Repository mirror automation
- Snapshot-based publish workflow
- Job and step tracking
- Operational dashboard
- YAML-based repository configuration
- GitLab/GitHub integration in future phases
- Standalone deployment with Docker Compose

## Development

Copy the environment file:

```bash
cp .env.example .env
```

Run the API:
```bash
docker compose up --build
```
Health check:
```bash
curl http://localhost:8000/api/v1/health
```
Expected response:
```json
{
  "status": "ok",
  "service": "aptly-pilot",
  "project": "AptlyPilot"
}
```
API docs:
```
http://localhost:8000/docs
```
