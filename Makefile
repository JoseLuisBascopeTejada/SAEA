.PHONY: help setup dev prod test lint clean download-models

help:
	@echo "Available commands:"
	@echo "  make setup            Install backend deps, download ONNX models, install frontend deps (pnpm)"
	@echo "  make dev              Start dev environment with Docker Compose"
	@echo "  make prod             Start production build with Docker Compose"
	@echo "  make test             Run backend and frontend test suites"
	@echo "  make lint             Run linters/formatters on backend and frontend"
	@echo "  make clean            Remove containers, volumes, and caches"

setup:
	pip install -r backend/requirements/dev.txt
	pre-commit install
	python backend/scripts/download_models.py
	pnpm --dir frontend install

dev:
	docker compose up --build

prod:
	docker compose -f docker-compose.yml up --build -d

test:
	docker exec saea_backend pytest
	pnpm --dir frontend test

lint:
	black backend/app
	flake8 backend/app
	mypy backend/app
	pnpm --dir frontend lint

clean:
	docker compose down -v
	rm -rf frontend/node_modules backend/.pytest_cache
