.PHONY: install lint test integration-up integration-test integration-down grpc run compose-up compose-down seed

install:
	uv sync

# 생성 코드가 없으면 ruff가 transport.grpc.generated.* 를 서드파티로 분류해
# import 정렬(I001)을 잘못 지적한다. 그래서 lint도 grpc 생성에 의존한다.
lint: grpc
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

seed:
	docker compose exec -T postgres psql -U advisory -d advisory < db/seed.sql

compose-down:
	docker compose down -v
