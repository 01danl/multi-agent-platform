.PHONY: help dev-backend dev-frontend test lint typecheck format build migrate docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

dev-backend: ## Run FastAPI backend with auto-reload on :8100
	cd backend && uv run uvicorn app.main:app --reload --port 8100

dev-frontend: ## Run Vite dev server on :5173 (proxies /api to :8100)
	cd frontend && npm run dev

test: ## Run backend test suite
	cd backend && uv run pytest -q

lint: ## Ruff (backend) + oxlint (frontend)
	cd backend && uv run ruff check app tests
	cd frontend && npm run lint --if-present

typecheck: ## mypy (backend) + tsc (frontend)
	cd backend && uv run mypy app
	cd frontend && npx tsc -b

format: ## Auto-format backend with ruff
	cd backend && uv run ruff check app tests --fix

build: ## Production build of the frontend
	cd frontend && npm ci && npm run build

migrate: ## Apply database migrations
	cd backend && uv run alembic upgrade head

migration: ## Create a migration: make migration m="message"
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

docker-up: ## Build and start all services (backend :8100, web :8080)
	docker compose up --build -d

docker-down: ## Stop services and remove containers
	docker compose down

clean: ## Remove build artifacts and local data
	rm -rf frontend/dist backend/.pytest_cache backend/.ruff_cache backend/.mypy_cache
