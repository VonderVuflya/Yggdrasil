# Lets Glama (and any container host) build, start, and introspect the Yggdrasil
# MCP server. The stdio facade answers `initialize` and `tools/list` on its own —
# no engine, no token, no network needed for introspection — so Glama's checks
# pass on a cold start. Actual tool calls lazily spawn the local engine.
FROM python:3.12-slim

WORKDIR /app
COPY . /app

# Build the server from source in this repo (zero runtime deps — pure stdlib).
RUN pip install --no-cache-dir .

# MCP stdio transport: the host speaks JSON-RPC over stdin/stdout.
ENTRYPOINT ["ygg", "mcp"]
