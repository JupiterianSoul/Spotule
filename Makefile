.PHONY: up down logs api web worker migrate revision test lint

up:            ## Start the whole stack
	docker compose up --build -d

down:          ## Stop the stack
	docker compose down

logs:          ## Tail logs
	docker compose logs -f --tail=200

api:           ## Run API locally (needs .env, Postgres, Redis)
	cd backend && uvicorn app.main:app --reload --port 8000

worker:        ## Run Celery worker + beat locally
	cd backend && celery -A app.workers.celery_app:celery_app worker -B -Q realtime,default -l info

web:           ## Run Next.js dev server
	cd frontend && pnpm dev

migrate:       ## Apply migrations
	cd backend && alembic upgrade head

revision:      ## Autogenerate a migration: make revision m="add foo"
	cd backend && alembic revision --autogenerate -m "$(m)"

test:          ## Run backend tests
	cd backend && pytest -q

lint:          ## Lint everything
	cd backend && ruff check . && cd ../frontend && pnpm lint
