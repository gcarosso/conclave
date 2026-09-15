.PHONY: cockpit handoff audit

# Render <hub>/STATUS.md from live state.
cockpit:
	@bash $(CURDIR)/cockpit.sh

# Write <checkout>/handoffs/<UTC>-handoff.md (make handoff TASK="what is pending").
handoff:
	@bash $(CURDIR)/session-handoff.sh $(if $(TASK),--task "$(TASK)")

# Snapshot, regenerate, diff the registry; exit code = issue count.
audit:
	@bash $(CURDIR)/registry-audit.sh
