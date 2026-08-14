.PHONY: install lint test integration-up integration-test integration-down grpc run compose-up compose-down

install:
	uv sync

lint:
	uv run ruff check src tests

test: grpc
	uv run pytest -m "not integration"

integration-up:
	docker compose -f docker-compose.test.yml up -d --wait

integration-test: grpc integration-up
	TEST_DATABASE_URL=postgresql://advisory:advisory@localhost:5434/advisory_test uv run pytest -m integration

integration-down:
	docker compose -f docker-compose.test.yml down -v

grpc:
	./scripts/generate_grpc.sh

run: grpc
	uv run python -m advisory_service.main

compose-up:
	docker compose up --build

compose-down:
	docker compose down -v
