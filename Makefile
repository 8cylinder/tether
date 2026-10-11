.PHONY: help install sync lint format format-check typecheck test check build run shell info clean

help:
	@echo "tether - command runner"
	@echo ""
	@echo "  make install       Install dependencies with uv"
	@echo "  make lint          Run ruff checks"
	@echo "  make format        Format code with ruff"
	@echo "  make format-check  Check formatting without writing"
	@echo "  make typecheck     Run the ty type checker"
	@echo "  make test          Run the test suite"
	@echo "  make check         lint + format-check + typecheck + test"
	@echo ""
	@echo "  make build         Build the container image"
	@echo "  make run           Run the default agent"
	@echo "  make shell         Open a shell in the container"
	@echo "  make info          Show configuration and status"
	@echo "  make clean         Remove the container image"

install:
	uv sync

sync: install

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

typecheck:
	uv run ty check

test:
	uv run pytest

check: lint format-check typecheck test

build:
	uv run tether build

run:
	uv run tether run

shell:
	uv run tether shell

info:
	uv run tether info

clean:
	uv run tether clean
