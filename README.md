# AptlyPilot

<p align="center">
  <img src="docs/images/aptlypilot-banner.png" alt="AptlyPilot" />
</p>

<h3 align="center">
Repository as Code Platform for Debian Package Management
</h3>

<p align="center">
Automate, manage, and monitor the complete lifecycle of Aptly repositories.
</p>

<p align="center">

![Python](https://img.shields.io/badge/python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-green)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-blue)

</p>


## Overview

**AptlyPilot** is a modern management and automation platform for
[aptly](https://www.aptly.info/) repositories.

It provides a centralized control plane for managing Debian package
repositories through declarative configuration, automation workflows,
and operational visibility.

AptlyPilot helps infrastructure teams automate the complete repository
lifecycle:

```
Mirror  ->  Snapshot  ->  Validation  ->  Publish
```


## Why AptlyPilot?

[Aptly](https://www.aptly.info/) is a powerful Debian repository management tool that provides a reliable and efficient way to create, manage, snapshot, and publish Debian package repositories. With features such as mirror management, snapshots, package version control, and atomic publishing, Aptly has become a trusted solution for managing Debian-based software repositories.

However, operating Aptly at scale requires additional capabilities for automation, abstraction, visibility, and operational control.

[AptlyPilot](https://github.com/mmayabi/AptlyPilot) was created to provide a modern management layer on top of Aptly, adding:

- Centralized repository management
- Declarative configuration and Repository as Code workflows
- Automated synchronization and scheduling
- Snapshot lifecycle management
- Operational visibility and monitoring
- Workflow automation and integration capabilities

AptlyPilot turns Aptly from a powerful repository engine into an operational platform for managing the complete lifecycle of Debian repositories.

## How to define Repository as Code?

Define repository lifecycle using declarative configuration.

For more information, refer to the [Repository as Code documentation](./docs/repository_as_code_manual.md).

Example:

```yaml
repository:
  name: debian-bookworm

mirror:
  url: http://deb.debian.org/debian
  distribution: bookworm
  components:
    - main
    - contrib

snapshot:
  retention: 10
```


## Demo

_Add your demo video or GIF here._

Example:

```markdown
![AptlyPilot Demo](docs/images/demo.gif)
```

## Installation

Clone this project:
```bash
git clone https://github.com/mmayabi/AptlyPilot.git

cd AptlyPilot
```
Copy the environment file and edit it:

```bash
cp .env.example .env
```
Start AptlyPilot application:
```
docker compose up --build -d
```

## API

AptlyPilot provides APIs for automation and integration.

API docs:
```
http://localhost:8000/docs
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


## Project Status

AptlyPilot is under active development.

The goal is to provide a reliable platform for automated Debian repository
lifecycle management.


## Contributing

Contributions are welcome.

sPlease open an issue or submit a pull request.
