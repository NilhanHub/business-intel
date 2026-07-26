# 1BT Opportunity Radar — Hostinger adapter

This directory contains the Node.js runtime adapter used to publish the existing
Business Intel web interface on Hostinger Business Web Hosting.

The adapter preserves the frontend HTTP contract, verified-lead validation,
tender rejection, live fixed-source refresh, shared-account authentication,
CSRF protection, notes, and atomic JSON storage. It does not replace or modify
the Python ADK application.

Production secrets are supplied only in an ignored release workspace as
`runtime-config.json`; they are never committed. Build the release archive with:

```powershell
uv run python tools/build_hostinger_slradar_release.py
```

Run the adapter tests with:

```powershell
node --test deploy/hostinger-slradar/tests/*.test.mjs
```
