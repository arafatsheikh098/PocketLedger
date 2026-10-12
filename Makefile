.PHONY: install test lint up down backup restore smoke fresh-clone

install:
	python3.12 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check app tests alembic

up:
	docker compose up --build

down:
	docker compose down

backup:
	./scripts/backup.sh

restore:
	./scripts/restore.sh

smoke:
	./scripts/smoke_test.sh

fresh-clone:
	./scripts/fresh_clone_test.sh
