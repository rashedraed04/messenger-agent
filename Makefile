.PHONY: dev test lint install clean

# Install all dependencies including dev
install:
	pip install -r requirements.txt

# Run development server with hot reload
dev:
	uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# Run test suite
test:
	pytest tests/ -v --tb=short

# Run tests with coverage report
test-cov:
	pytest tests/ -v --cov=app --cov-report=term-missing

# Lint with ruff
lint:
	ruff check app/ tests/

# Format with ruff
fmt:
	ruff format app/ tests/

# Build Docker image locally
docker-build:
	docker build -t messenger-agent .

# Run Docker container locally
docker-run:
	docker run --env-file .env -p 8080:8080 messenger-agent

# Clean Python caches
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage htmlcov/
