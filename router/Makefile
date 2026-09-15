.PHONY: test generate drift-check smoke jobs

PY := python3
HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

test:
	@cd $(HERE) && $(PY) tests.py

generate:
	@cd $(HERE) && $(PY) generate.py --write

drift-check:
	@cd $(HERE) && $(PY) generate.py --check

smoke:
	@cd $(HERE) && ./ai smoke

jobs:
	@tail -20 $(HERE)jobs/index.jsonl 2>/dev/null || echo "no jobs yet"
