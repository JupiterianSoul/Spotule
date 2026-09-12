#!/bin/sh
# Container entrypoint for the web service.
#
# Next's standalone server binds `process.env.HOSTNAME`, and container runtimes set that
# variable to the container or service name. On Render it is not resolvable from inside the
# container, so the server exits with "getaddrinfo ENOTFOUND" and the platform serves 502 with
# nothing in the application log. Forcing the wildcard address here beats relying on a
# Dockerfile ENV, which a platform-injected value would override.
set -e
export HOSTNAME=0.0.0.0
exec node server.js
