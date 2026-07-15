# Cross-surface: reach Yggdrasil from the web & mobile

Local Yggdrasil speaks **stdio MCP** (`ygg mcp`), which only local CLI hosts
(Claude Code, Codex) can launch. The web/mobile apps (claude.ai, ChatGPT)
connect to **remote MCP** servers by **HTTPS URL** — their backend dials your
server, so it must be publicly reachable and authenticated.

`ygg mcp-http` is the missing piece: it exposes the **same tools** over the MCP
**Streamable HTTP** transport. This doc takes you from that to a working
claude.ai custom connector.

> Status: the HTTP facade ships and works (bearer-auth). The **OAuth** layer that
> claude.ai's custom connectors require is the remaining piece — options below.

## 1. Run the HTTP facade

```bash
ygg mcp-http            # serves http://127.0.0.1:42071/mcp  (bearer-protected)
```
- Binds **localhost** (a tunnel exposes it; never bind 0.0.0.0 directly).
- Auth: presents `Authorization: Bearer <token>`. Defaults to your engine token
  (`ygg token`); override with `YGG_MCP_TOKEN`. Port via `YGG_MCP_HTTP_PORT`.
- `GET /health` is open; `POST /mcp` is the MCP endpoint.

Smoke-test it:
```bash
curl -s http://127.0.0.1:42071/mcp -H "Authorization: Bearer $(ygg token)" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool
```

## 2. Make it public (pick a topology)

| Topology | How | Trade-off |
|---|---|---|
| **A. Local + tunnel** | keep the engine local, expose `:42071` via a tunnel | data 100% local; **only works while your machine is awake** |
| **B. Always-on node** | run the engine + facade on a cheap VPS / Raspberry Pi | reachable even when your laptop is off; data lives on your (self-hosted) node |
| **C. Hosted sync** | a managed multi-tenant endpoint | zero-setup for users; biggest build |

### Tunnel (topology A, fastest)
```bash
# quick throwaway URL (no account):
cloudflared tunnel --url http://127.0.0.1:42071
# -> https://<random>.trycloudflare.com  → your /mcp is at that URL + /mcp

# stable URL (named tunnel, needs a Cloudflare account + a domain):
cloudflared tunnel create yggdrasil
cloudflared tunnel route dns yggdrasil ygg.example.com
cloudflared tunnel run --url http://127.0.0.1:42071 yggdrasil
```

## 3. Authentication for claude.ai

claude.ai custom connectors expect **OAuth 2.1** (per the MCP auth spec:
protected-resource metadata + either Dynamic Client Registration or a Client
ID/Secret you paste under *Advanced settings*). A raw bearer token is **not**
enough for claude.ai (it is enough for `mcp-remote` and some other clients).

Don't hand-roll OAuth — front the facade with one of:
- **Cloudflare Access / `workers-oauth-provider`** — Cloudflare terminates OAuth
  and forwards authenticated requests to your tunnel. Least code.
- **An OAuth provider** (Auth0 / Clerk / Stytch / WorkOS) as the authorization
  server; the facade validates the issued JWT (a small change to `_auth_ok`).

This is the one remaining build step for full claude.ai support; everything
below it (transport, tools, tunnel) is done.

## 4. Connect claude.ai

1. claude.ai → **Settings → Connectors → Add custom connector → Web**.
2. Paste your public MCP URL (e.g. `https://ygg.example.com/mcp`).
3. Under **Advanced settings**, supply the OAuth Client ID/Secret from step 3
   (or rely on Dynamic Client Registration if your AS supports it).
4. Authorize. The `ygg_*` tools now work from web and mobile, against the **same
   memory** as your CLI agents.

## Security

- Always require auth before exposing the facade publicly (bearer at minimum;
  OAuth for claude.ai). An open memory endpoint on the internet is a data leak.
- Prefer a tunnel with its own access control over opening a raw port.
- The facade binds localhost; the tunnel is the only public surface.
- Scope/rotate the token (`ygg token` lives in `~/.yggdrasil/token`, mode 600).
