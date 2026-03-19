# AI Audio Hub - Docker Deployment Makefile

.PHONY: help build up down logs clean dev prod restart status

# Default target
help: ## Show this help message
	@echo "AI Audio Hub - Docker Deployment"
	@echo ""
	@echo "Available commands:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

build: ## Build Docker images
	docker-compose build

up: ## Start services in foreground
	docker-compose up

up-d: ## Start services in background
	docker-compose up -d

down: ## Stop all services
	docker-compose down

logs: ## Show logs from all services
	docker-compose logs -f

logs-backend: ## Show backend logs only
	docker-compose logs -f backend

logs-frontend: ## Show frontend logs only
	docker-compose logs -f frontend

dev: ## Start development environment
	docker-compose up --build

prod: ## Start production environment
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

restart: ## Restart all services
	docker-compose restart

status: ## Show status of services
	docker-compose ps

clean: ## Remove containers, networks, and volumes
	docker-compose down -v --remove-orphans
	docker system prune -f

deep-clean: ## Remove everything including images
	docker-compose down -v --remove-orphans
	docker system prune -a -f --volumes

install: ## Install dependencies locally (for development)
	pip install -r requirements.txt

test: ## Run basic health checks
	@echo "Testing backend health..."
	@curl -f http://localhost:8080/ || echo "Backend not responding"
	@echo "Testing frontend..."
	@curl -f http://localhost/ || echo "Frontend not responding"

env: ## Create .env file from template
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "Created .env file. Please edit it with your configuration."; \
	else \
		echo ".env file already exists."; \
	fi