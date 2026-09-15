# Security

Conclave runs vendor clients on the operator's machine. Its controls cover routing eligibility, configured model approval, job checks, advisory writer locks, and optional publication scans. The host, vendor clients, configuration, and local filesystem remain part of the trust boundary.

Report vulnerabilities through the repository's Security tab. Include a minimal reproduction with synthetic data; keep credentials and private prompts out of public issues.

## Relevant defects

- Dispatch to a vendor excluded by the job's data class or domain.
- Invocation of a gated model without recorded approval.
- An acceptance decision inconsistent with the declared checks.
- Concurrent ownership of the same router write set.
- A clean gate result despite a matching marker within its documented scan scope, or a suppressed scan error.

## Limits

- An empty working directory does not restrict a process's filesystem reads. Vendor tools, shell access, global configuration, and permissions need separate review.
- Generated Claude file-tool deny rules do not control every shell command or external tool.
- Local job files are mutable. A response hash does not authenticate the writer or verify repository changes.
- Command checks execute trusted shell commands supplied through the kernel API.
- Publication scans search configured regexes in raw bytes. They do not decode archives, discover arbitrary sensitive content, or protect a repository whose hooks are absent or bypassed.

See [architecture](docs/architecture.md#enforcement-boundary) for the specific controls and scan modes. Vendor-client vulnerabilities should also be reported upstream.
