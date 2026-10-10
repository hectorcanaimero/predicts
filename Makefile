.PHONY: api-test api-lint web-test web-lint test lint

api-test:
	cd api && uv run pytest -q

api-lint:
	cd api && uv run ruff check .

web-test:
	cd web && npm test -- --run

web-lint:
	cd web && npm run lint

test: api-test web-test

lint: api-lint web-lint
