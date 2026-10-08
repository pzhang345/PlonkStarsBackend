# Always run from the Backend/ directory, regardless of caller's cwd.
BACKEND_DIR := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
SHELL := sh
.SHELLFLAGS := -ec
.ONESHELL:

CONTAINER_NAME := plonkstars-test-db
COMPOSE_FILE := tests/docker-compose.test.yml

# venv interpreter: Windows layout first, then POSIX.
PYTHON := $(firstword $(wildcard $(BACKEND_DIR).venv/Scripts/python.exe $(BACKEND_DIR).venv/bin/python))

# Extra pytest arguments, e.g. `make test ARGS="-m unit"`.
ARGS ?=

.PHONY: test test-changed db-up db-down

test: db-up
	@cd "$(BACKEND_DIR)"
	# Run pytest through the venv interpreter, forwarding any extra args.
	status=0
	"$(PYTHON)" -m pytest $(ARGS) || status=$$?
	echo
	echo "Test DB left running. Stop it with:"
	echo "  make db-down"
	exit $$status

# Run only tests affected by code changes since the last run (pytest-testmon).
# The first run, or a run after deleting .testmondata, runs the full suite to
# build the baseline. Only Python changes are tracked: run `make test` after
# changing config, migrations, or test DB data.
test-diff: db-up
	@cd "$(BACKEND_DIR)"
	status=0
	"$(PYTHON)" -m pytest --testmon $(ARGS) || status=$$?
	echo
	echo "Test DB left running. Stop it with:"
	echo "  make db-down"
	exit $$status

db-up:
	@cd "$(BACKEND_DIR)"
	# Make sure Docker Desktop / the Docker daemon is actually up.
	if ! docker info >/dev/null 2>&1; then
		echo "Docker does not appear to be running. Start Docker and try again."
		exit 1
	fi
	# Reuse a running container, restart a stopped one, or start a fresh one.
	if [ -n "$$(docker ps --filter 'name=^$(CONTAINER_NAME)$$' --format '{{.Names}}')" ]; then
		echo "Reusing already-running $(CONTAINER_NAME) container."
	elif [ -n "$$(docker ps -a --filter 'name=^$(CONTAINER_NAME)$$' --format '{{.Names}}')" ]; then
		echo "Starting existing $(CONTAINER_NAME) container..."
		docker start $(CONTAINER_NAME) >/dev/null
	else
		echo "Creating $(CONTAINER_NAME) container via docker compose..."
		docker compose -f $(COMPOSE_FILE) up -d --wait
	fi
	# Poll pg_isready until Postgres accepts connections, or give up.
	tries=0
	until docker exec $(CONTAINER_NAME) pg_isready -U plonktest -d plonkstars_test >/dev/null 2>&1; do
		tries=$$((tries + 1))
		if [ $$tries -ge 30 ]; then
			echo "Timed out waiting for $(CONTAINER_NAME) to become ready."
			exit 1
		fi
		sleep 1
	done

db-down:
	@cd "$(BACKEND_DIR)"
	docker compose -f $(COMPOSE_FILE) down
