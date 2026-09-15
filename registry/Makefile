.PHONY: refresh probe audit

# Rebuild registry.json + REGISTRY.md from live probes.
refresh:
	python3 $(CURDIR)/generate.py

# Print the probe JSON to stdout; writes nothing.
probe:
	python3 $(CURDIR)/generate.py --probe

# Snapshot, regenerate, diff, count issues (exit code = issue count).
audit:
	bash $(CURDIR)/../ops/registry-audit.sh
