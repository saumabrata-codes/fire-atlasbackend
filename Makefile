.PHONY: up db-up migrate api frontend

up:
	docker compose up -d --build --wait

db-up:
	docker compose up -d db

migrate:
	docker compose exec -T backend python -m alembic upgrade head

api:
	docker compose up -d --build backend

frontend:
	docker compose up -d --build frontend
