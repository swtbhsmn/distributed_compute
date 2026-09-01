SHELL := /bin/sh

PYTHON ?= python3
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python
COORDINATOR_BIN := $(VENV)/bin/compute-coordinator
WORKER_BIN := $(VENV)/bin/compute-worker

TOKEN ?= $(DISTRIBUTED_COMPUTE_TOKEN)
HOST ?= 0.0.0.0
PORT ?= 8001
COORDINATOR_URL ?= http://127.0.0.1:$(PORT)
WORKER_NAME ?= local-worker
CORS_ORIGINS ?= http://localhost:5173,http://127.0.0.1:5173

.DEFAULT_GOAL := help

.PHONY: help setup setup-backend setup-worker setup-dashboard setup-all \
	coordinator worker dashboard start start-all dev \
	start-coordinator start-worker start-dashboard \
	android-setup android-worker test test-backend test-dashboard build-dashboard \
	check-token

help:
	@echo "Distributed Compute POC"
	@echo ""
	@echo "Setup"
	@echo "  make setup              Install backend development dependencies"
	@echo "  make setup-worker       Install a desktop worker with psutil"
	@echo "  make setup-dashboard    Install dashboard dependencies"
	@echo "  make setup-all          Install backend and dashboard dependencies"
	@echo "  make android-setup      Install the lightweight Termux worker"
	@echo ""
	@echo "Run (TOKEN is required)"
	@echo "  make coordinator TOKEN=secret"
	@echo "  make worker TOKEN=secret COORDINATOR_URL=http://192.168.1.20:8000"
	@echo "  make dashboard"
	@echo "  make start TOKEN=secret       Coordinator + dashboard"
	@echo "  make start-all TOKEN=secret   Coordinator + worker + dashboard"
	@echo "  make android-worker TOKEN=secret COORDINATOR_URL=http://192.168.1.20:8000"
	@echo ""
	@echo "Verify"
	@echo "  make test"
	@echo "  make build-dashboard"

$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

setup-backend setup: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install '.[dev]'

setup-worker: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install '.[desktop]'

setup-dashboard:
	npm --prefix dashboard install

setup-all: setup-backend setup-dashboard

check-token:
	@if [ -z "$(TOKEN)" ]; then echo "TOKEN is required. Example: make coordinator TOKEN=my-secret"; exit 1; fi

coordinator start-coordinator: check-token
	@DISTRIBUTED_COMPUTE_TOKEN="$(TOKEN)" \
	DISTRIBUTED_COMPUTE_CORS_ORIGINS="$(CORS_ORIGINS)" \
	$(COORDINATOR_BIN) --host "$(HOST)" --port "$(PORT)"

worker start-worker: check-token
	@DISTRIBUTED_COMPUTE_TOKEN="$(TOKEN)" \
	$(WORKER_BIN) --coordinator "$(COORDINATOR_URL)" --name "$(WORKER_NAME)"

dashboard start-dashboard:
	VITE_PROXY_TARGET="$(COORDINATOR_URL)" npm --prefix dashboard run dev

start:
	@$(MAKE) --no-print-directory -j2 coordinator dashboard \
		TOKEN="$(TOKEN)" HOST="$(HOST)" PORT="$(PORT)" CORS_ORIGINS="$(CORS_ORIGINS)"

start-all dev:
	@$(MAKE) --no-print-directory -j3 coordinator worker dashboard \
		TOKEN="$(TOKEN)" HOST="$(HOST)" PORT="$(PORT)" \
		COORDINATOR_URL="$(COORDINATOR_URL)" WORKER_NAME="$(WORKER_NAME)" \
		CORS_ORIGINS="$(CORS_ORIGINS)"

android-setup:
	$(PYTHON) -m pip install .

android-worker: check-token
	@DISTRIBUTED_COMPUTE_TOKEN="$(TOKEN)" \
	$(PYTHON) -m distributed_compute.worker \
		--coordinator "$(COORDINATOR_URL)" --name "$(WORKER_NAME)"

test-backend:
	$(VENV_PYTHON) -m pytest

test-dashboard:
	npm --prefix dashboard run lint

test: test-backend test-dashboard

build-dashboard:
	npm --prefix dashboard run build
