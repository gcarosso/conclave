# conclave — top-level targets. Every target is safe to run from any directory.
.PHONY: test router-test gate-test drift-check generate smoke cockpit registry audit init lint

HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

test: router-test gate-test          ## offline: router tests + publish-gate fixtures (no vendor, no network)

router-test:
	@$(MAKE) -s -C $(HERE)router test

gate-test:
	@bash $(HERE)gate/tests/gate-test.sh

drift-check:                         ## generated instruction files match shared/governance.json
	@$(MAKE) -s -C $(HERE)router drift-check

generate:                            ## regenerate instruction files after editing governance.json
	@$(MAKE) -s -C $(HERE)router generate

smoke:                               ## tier-1 ping per vendor (needs the vendor CLIs / key)
	@$(HERE)router/ai smoke

cockpit:                             ## render <hub>/STATUS.md
	@bash $(HERE)ops/cockpit.sh

registry:                            ## re-probe vendors, MCP servers, skills, jobs, models
	@python3 $(HERE)registry/generate.py

audit:                               ## registry snapshot → refresh → diff → issue count
	@bash $(HERE)ops/registry-audit.sh

init:                                ## bootstrap a hub around this checkout
	@$(HERE)router/ai init

lint:
	@command -v shellcheck >/dev/null && shellcheck -S warning $(HERE)gate/*.sh $(HERE)gate/tests/*.sh $(HERE)ops/*.sh $(HERE)install.sh || echo "shellcheck not installed; skipped"
	@python3 -m py_compile $(HERE)router/kernel.py $(HERE)router/adapters.py $(HERE)router/verify.py $(HERE)router/generate.py $(HERE)router/ai $(HERE)registry/generate.py && echo "python: ok"
