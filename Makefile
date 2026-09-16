# conclave — top-level targets. Every target is safe to run from any directory.
.PHONY: test router-test gate-test check-links e2e e2e-live drift-check generate smoke cockpit registry audit init lint

HERE := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))

test: router-test gate-test check-links   ## offline: router tests, publish-gate fixtures, docs links (no vendor, no network)

router-test:
	@$(MAKE) -s -C $(HERE)router test

gate-test:
	@bash $(HERE)gate/tests/gate-test.sh

check-links:                         ## relative Markdown links and #anchors resolve
	@python3 $(HERE)scripts/check-links.py $(HERE)

e2e:                                 ## temp hub + real `ai` CLI through fake claude/codex CLIs (offline)
	@bash $(HERE)scripts/e2e.sh

e2e-live:                            ## same hub, one real tier-1 scout job through your logged-in vendors
	@bash $(HERE)scripts/e2e.sh --live

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
	@if command -v shellcheck >/dev/null; then shellcheck -S warning $(HERE)gate/*.sh $(HERE)gate/tests/*.sh $(HERE)ops/*.sh $(HERE)scripts/*.sh $(HERE)install.sh; else echo "shellcheck not installed; skipped"; fi
	@python3 -m py_compile $(HERE)router/kernel.py $(HERE)router/adapters.py $(HERE)router/verify.py $(HERE)router/generate.py $(HERE)router/ai $(HERE)registry/generate.py $(HERE)scripts/check-links.py $(HERE)scripts/fake-vendors/_fake.py && echo "python: ok"
