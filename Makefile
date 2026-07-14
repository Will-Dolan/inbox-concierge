.PHONY: setup dev test lint

setup:
	cd api && uv sync --extra dev
	cd frontend && npm install

dev:
	docker compose up -d postgres
	cd api && uv run alembic upgrade head
	( cd api && uv run uvicorn main:app --reload ) & \
	API_PID=$$!; \
	( cd frontend && npm run dev ) & \
	FRONTEND_PID=$$!; \
	trap 'kill $$API_PID $$FRONTEND_PID 2>/dev/null' INT TERM EXIT; \
	wait

test:
	cd api && uv run ruff check .
	cd api && uv run pytest
	cd frontend && npm run lint
	cd frontend && npm run build

lint:
	cd api && uv run ruff check .
	cd frontend && npm run lint
