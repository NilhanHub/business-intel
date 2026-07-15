# Hostinger Deployment — Unsupported Future Draft

> **Do not deploy from this document.** Business Intel is currently local-only, binds to `127.0.0.1`, uses a local shared-account security model, and has no supported production deployment path.

This filename is retained only so earlier references do not disappear. The previous step-by-step Hostinger instructions were removed because they conflicted with the current security and product boundary.

Any future deployment proposal must be reviewed and implemented as a separate project phase. At minimum it would need:

- an explicit production identity and tenancy model;
- HTTPS-only cookies, reverse-proxy trust, host/origin policy, and edge request limits;
- managed secrets and durable storage outside the application package;
- production logging, monitoring, backups, restore testing, and incident procedures;
- deployment-specific dependency, infrastructure, and security verification.

Until that work is explicitly approved, use the local runbook in `README.md` only.
