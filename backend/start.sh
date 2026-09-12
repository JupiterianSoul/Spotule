#!/bin/sh
# Container entrypoint for the API.
#
# A script rather than an inline `sh -c "a && b"` in render.yaml: Render already runs
# dockerCommand through a shell, so the extra wrapper made the entire string get looked up as
# a single command name ("sh: 1: alembic upgrade head && uvicorn ...: not found"). One file,
# no quoting ambiguity, and it can be tested locally.
set -e

# Apply any pending migrations before serving. `set -e` means a failed migration exits the
# container instead of starting an app against the wrong schema.
alembic upgrade head

# Render injects PORT (10000); locally there is none, so fall back to 8000.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
