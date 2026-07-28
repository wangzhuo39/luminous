# Cloudflare Tunnel for the private mobile test

The tester does not install Cloudflare, a VPN, or a certificate. Only the host
machine runs `cloudflared`; the tester opens one fixed HTTPS URL and enters the
Luminous invite code once.

1. Install `cloudflared` on the host from Cloudflare's official package.
2. Authenticate the host and create a named tunnel:

   ```bash
   cloudflared tunnel login
   cloudflared tunnel create luminous-private-test
   cloudflared tunnel route dns luminous-private-test luminous.example.com
   ```

3. Copy the generated tunnel credential to
   `/etc/luminous/cloudflared/credentials.json`, owned by `root:root` with mode
   `0600`.
4. Copy `config.yml` to `/etc/cloudflared/config.yml`, replace the UUID and
   hostname, then set the same HTTPS origin in
   `/etc/luminous/luminous.env` as both `LUMINOUS_CORS_ORIGINS` and
   `LUMINOUS_PUBLIC_URL`.
5. Validate and enable the tunnel:

   ```bash
   cloudflared tunnel ingress validate
   systemctl enable --now cloudflared
   /opt/luminous/current/scripts/deploy/smoke-test.sh
   ```

The API remains bound to `127.0.0.1:8000`; do not open port 8000 in the router
or host firewall. Treat `credentials.json`, the invite code, session secret,
admin token, and model key as server-only credentials.
