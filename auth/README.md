# Bshome Telegram sign-in

The Docker auth gateway protects every page and API route except the minimal `/api/health` probe. The application container has no published host ports. Use the canonical Tailscale IP URL; loopback requests redirect there so login always uses the same browser origin.

- TGsecrets: http://100.115.155.120:7999
- Personal Telegram: http://100.115.155.120:3060

Choose **Continue with Bshome** to use Bshome's existing Telegram login. Access requires the active Bshome user with Telegram ID `1082729605` (@invidtiv); username changes cannot grant access to another account. Bshome rechecks active membership when authorizing and exchanging the code.

The login handoff uses browser-bound state, S256 PKCE, a one-use 60-second code, and a per-app HMAC-authenticated server exchange. App sessions are opaque, HttpOnly, SameSite=Lax cookies expiring after one hour. Restarting a gateway invalidates its sessions. `POST /auth/logout` with the app's exact Origin header clears the session. Mutating requests require that same Origin. The published HTTP endpoint is private to localhost/Tailscale; tailnet traffic is encrypted by Tailscale. Cookies are host-only and separately named for each app; HTTPS deployments additionally set Secure.

Deployment configuration lives outside Git under `/home/bsdev/.config/private-telegram-auth/` (mode 0700 directory, mode 0600 files):

- `authority.json`: Bshome's PRIVATE_APPS_AUTH_CONFIG, mapping each app to its fixed origin and separate random 32-byte hexadecimal key.
- `<client>.json`: gateway config with client, origin, upstream, and matching key.

The gateway runs as host UID/GID 1001 to read its private bind-mounted config. Never commit the configuration or print its keys. Rebuild with `docker compose build auth-gateway`, then deploy with `docker compose up -d --no-build`. Run `node --test auth/gateway.test.cjs` for access-boundary tests.

Bshome mounts `server/lib/private-app-auth.cjs` before its JSON body parser. Authority tests: `node --test server/lib/private-app-auth.test.cjs` in the Bshome repo.

Deployment validation on 2026-11-07: both app APIs return 401 without a session, both sign-in routes reach Bshome's login, and all three services respond to health checks. A real Telegram login remains a manual acceptance check.
