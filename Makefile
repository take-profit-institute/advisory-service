.PHONY: install lint test grpc run compose-up compose-down

install:
	uv sync

lint:
	uv run ruff check src tests

test:
	uv run pytest

grpc:
	./scripts/generate_grpc.sh

run: grpc
	uv run python -m advisory_service.main

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v