.PHONY: dev test install security lint

dev:
	.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/pytest tests/ -v

install:
	.venv/bin/pip install -r requirements.txt

security:
	.venv/bin/pip install bandit pip-audit
	.venv/bin/bandit -r app/ -ll
	.venv/bin/pip-audit -r requirements.txt

lint:
	.venv/bin/python -m compileall app tests
