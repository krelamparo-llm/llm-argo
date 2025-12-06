# PLAN: Browser Access for Chat CLI over Tailscale

## Goal
- Make the existing Chat CLI reachable from an iPad browser via Tailscale without exposing Argo Brain or llama-server/Chroma beyond the tailnet.

## Constraints / assumptions
- llama-server stays local (e.g., 127.0.0.1:8080 per README) and must not be directly exposed.
- ChromaDB stays local at the configured path; only the new web layer is reachable over Tailscale.
- Tailscale is already running on Argo; MagicDNS is available (e.g., `argo.tailnet-name.ts.net`).
- Prefer reusing the current Python stack and `AppRuntime`/Assistant wiring to avoid a divergent code path from `scripts/chat_cli.py`.
- Default to app-level auth even though Tailscale ACLs protect the host.

## Decisions locked
- Backend: FastAPI + uvicorn leveraging the existing AppRuntime/SessionManager.
- Transport: fetch streaming with SSE framing (Safari/Chrome on iPad compatible).
- Code placement: `argo_brain/web` package with static assets + `scripts/chat_service.py` launcher.
- Port/host: `0.0.0.0:3210` via `ARGO_WEB_HOST/ARGO_WEB_PORT`; llama/Chroma stay on localhost.
- Auth/TLS: bearer `ARGO_WEB_TOKEN` on all endpoints; TLS from `tailscale cert` for the tailnet hostname.
- ACLs: Tailscale rule opening port 3210 only to the iPad (device/user) on Argo/tagged host.

## Target architecture (browser -> web chat service -> Argo Brain)
- Browser (iPad) connects over Tailscale to a small web chat service running on Argo (e.g., FastAPI/uvicorn).
- Service binds on `0.0.0.0:<port>` (e.g., 3210) but only reachable via Tailscale IP/MagicDNS; serves both static chat UI and streaming chat API.
- Service proxies requests into the existing Argo Brain runtime (shared session/memory) and relays streamed tokens back to the browser.
- Authentication: static bearer token enforced on all endpoints; TLS via `tailscale cert` for the Tailscale hostname.
- llama-server and Chroma remain bound to localhost; only the web chat service listens on the tailnet.

## Implementation steps
### 0) Prep
- Pick port (e.g., 3210) and hostname (`argo.tailnet-name.ts.net`).
- Generate a long bearer token; store in env (`ARGO_WEB_TOKEN`) and keep out of git.
- Ensure Tailscale ACL allows your iPad device/user to reach the chosen port; block everyone else.
- Decide directory for static assets (e.g., `argo_brain/web_ui` or `scripts/web_ui`).

### 1) Build web chat backend (Python/FastAPI)
- Add dependencies if missing: `fastapi`, `uvicorn[standard]` (and `sse-starlette` if using SSE helper).
- Implement `scripts/chat_service.py` (or `argo_brain/web/chat_service.py`):
  - Initialize `AppRuntime` once; wire to `SessionManager` so browser sessions reuse the same memory stack as CLI.
  - Endpoints:
    - `GET /health` → readiness.
    - `POST /chat` → accepts `{session_id, message, mode, max_tokens}`; streams tokens back (SSE or WebSocket).
    - `POST /cancel` → optional, to stop a running generation by session/request id.
  - Streaming: prefer SSE (`text/event-stream`) for Safari compatibility; fall back to WebSocket if you need bidirectional control.
  - Security middleware: require `Authorization: Bearer <ARGO_WEB_TOKEN>`, reject missing/invalid tokens.
  - Limits: request timeout, cap max tokens/context, cap concurrent requests per session/IP; guard tool fan-out.
  - Logging: include session id, mode, token count, latency; redact prompts in logs if desired.

### 2) Serve lightweight browser UI
- Add static `index.html` + `app.js` + `app.css`; serve via FastAPI `StaticFiles`.
- UI requirements:
  - Chat history pane, input box, send button, and “stop”/cancel button.
  - Session selector/field (default from `localStorage`) so browser and CLI can share context.
  - Streaming renderer consuming SSE/WebSocket events; show typing cursor and errors inline.
  - Mobile-first layout: large tap targets, sticky footer input, works in Safari on iPad.
  - Basic Markdown rendering for responses; copy-to-clipboard for messages.

### 3) Secure transport and exposure
- Keep llama-server and Chroma on localhost; only expose the new service to Tailscale.
- Obtain TLS cert: `tailscale cert argo.tailnet-name.ts.net`; point uvicorn to `--ssl-certfile/--ssl-keyfile`.
- Enforce bearer token on every endpoint; rotate token periodically (store in `/home/krela/llm-argo/.argo_env`).
- Tailscale ACL:
  - Allow port 3210 from your iPad (device or user-based rule).
  - Optionally tag Argo (`tag:argo-brain`) and scope ACL to that tag.
- Ensure no router/NAT port-forwarding; service should not bind to public IPs beyond the tailnet.

### 4) Configuration and service management
- Env vars: `ARGO_WEB_HOST=0.0.0.0`, `ARGO_WEB_PORT=3210`, `ARGO_WEB_TOKEN=<token>`, `ARGO_WEB_TLS_CERT/KEY=<paths>`, reuse existing ARGO_* settings for runtime.
- Systemd unit `argo-chat-web.service`:
  - `WorkingDirectory=/home/krela/llm-argo/argo_brain`
  - `ExecStart=/path/to/venv/bin/python -m scripts.chat_service --host $ARGO_WEB_HOST --port $ARGO_WEB_PORT --ssl-certfile ...`
  - `EnvironmentFile=/home/krela/llm-argo/.argo_env`
  - `Restart=on-failure`, `User=krela`
- Dev mode alternative: `tmux`/`honcho` profile to run the service without systemd.
- Logging: forward uvicorn logs to journald (`journalctl -u argo-chat-web`) or rotating file.

### 5) Testing and verification
- Local health: `curl -H "Authorization: Bearer $ARGO_WEB_TOKEN" http://127.0.0.1:3210/health`.
- Tailscale reachability: `curl -H "Authorization: Bearer $ARGO_WEB_TOKEN" https://argo.tailnet-name.ts.net:3210/health` from another tailnet device.
- Browser smoke: open the UI, send "ping", confirm streamed tokens, use stop button to cancel mid-run.
- Session continuity: start a named session in CLI, continue in browser with same `session_id`, confirm memory recall.
- Failure drills: stop llama-server → UI should show “LLM unavailable”; send bad/expired token → 401.
- Load/latency: ensure long answers stream smoothly and timeouts are handled.

### 6) Rollout sequence
1) Prepare env file with token/port/cert paths; update ACL for port 3210.
2) Install deps; run `python scripts/chat_service.py --dev` locally and iterate UI.
3) Generate TLS via `tailscale cert`; switch service to HTTPS.
4) Create/enable systemd unit; verify `/health` locally then from another tailnet node.
5) Test on iPad Safari/Chrome; add a home-screen shortcut/bookmark to the chat page.
6) Document the access URL (`https://argo.tailnet-name.ts.net:3210`) in internal notes.

### 7) Back-out plan
- Stop/disable `argo-chat-web.service` and remove the ACL rule for port 3210.
- Delete TLS cert/key if desired; remove newly added deps if rolling back code.
- No impact to llama-server/Chroma/CLI because they remain local-only.

### 8) Open questions / next decisions
- Add true token streaming from llama-server vs final-chunk SSE shim.
- Do we need server-side cancellation hooks beyond client abort (e.g., cancel llama-server/tool calls)?
- Should browser ingest/upload be supported in v1 or kept CLI-only?
- Add per-user tokens/quotas and separate namespaces?
- Should the UI cache recent history locally for faster reloads?

### 9) Nice-to-haves (later)
- Auth UI prompting for token (stored in `sessionStorage`), logout button.
- Markdown rendering with syntax highlighting and copy buttons.
- Metrics endpoint (`/metrics`) and lightweight analytics on latency/tool usage.
- Theming (light/dim) with iPad-friendly spacing; keyboard shortcuts for send/stop.
- Pre-flight checks in UI for llama-server and Chroma availability with actionable errors.
