.PHONY: dev test install

dev:
	.venv/bin/uvicorn app.main:app --reload --port 8000

test:
	.venv/bin/pytest tests/ -v

install:
	.venv/bin/pip install -r requirements.txt
