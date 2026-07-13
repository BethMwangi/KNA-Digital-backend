.PHONY: format lint check

format:
	black .
	ruff check --fix .

lint:
	ruff check .
	black --check .

check: lint
