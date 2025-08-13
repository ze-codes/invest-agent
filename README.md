# invest-agent (Liquidity-Only MVP)

Remote-first Docker dev for use with Cursor Remote-SSH on a cloud VM.

## Stack

- FastAPI (api/main.py)
- Postgres 17 (Docker service)
- Docker + docker compose

## Quick start (any host with Docker)

1. Copy env:
   cp env.sample .env
2. Build & run:
   make up
3. Health check:
   open http://localhost:8000/health
4. Stop:
   make down

## Remote VM setup (recommended)

- Provision Ubuntu 22.04/24.04 VM (>=2 vCPU, 4GB RAM). Open port 22 only.
- Install Docker + compose:
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker $USER && newgrp docker
- Clone repo and start:
  git clone https://github.com/your-org/invest-agent.git
  cd invest-agent
  cp env.sample .env && edit .env
  make up
- Tunnel API to your laptop:
  ssh -N -L 8000:localhost:8000 user@your-vm
  Then visit http://localhost:8000/health

## Cursor Remote-SSH

- Add SSH host in Cursor → Remote-SSH: user@your-vm
- Open the repo folder on the VM and run `make up` in the terminal.

## Files

- api/main.py — FastAPI entrypoint
- docker-compose.yml — API + Postgres services
- Dockerfile — API image
- requirements.txt — Python deps
- env.sample — Example environment vars
- Makefile — convenience targets

Next: add Alembic migrations and schemas per `implementation-plan.md`.
