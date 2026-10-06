# Hosting the landing site

The landing site in [`site/`](../../site) is plain static files: HTML, CSS, one script, images and fonts. There's no build step and it makes no third-party requests.

These scripts serve it with [Caddy](https://caddyserver.com) on port 8080 and refresh it from GitHub every night. A [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) puts it on the internet: you don't need router port forwarding, your home IP isn't exposed, and HTTPS comes free.

> This is for the public landing page only. Keep the FinVault app itself private on your home network, and use something like Tailscale if you want to reach it away from home.

## Mac (for example a Mac mini)

You need [Homebrew](https://brew.sh). Then, in Terminal on the Mac:

```bash
curl -fsSL https://raw.githubusercontent.com/finvaultapp/finvault/main/deploy/site/install-mac.sh | bash
```

It does four things:
- installs Caddy and `cloudflared` with Homebrew
- downloads only the `site/` folder into `$(brew --prefix)/var/www/finvault-site`
- starts Caddy now and at every login (`brew services`), with the security headers from [`Caddyfile`](Caddyfile)
- refreshes the site from GitHub every night at 03:30, using a launchd job that logs to `~/Library/Logs/finvault-site-update.log`

Check it at http://localhost:8080. To publish a change right away, run `finvault-update-site`.

The Mac has to stay awake and come back after a power cut. In **System Settings → Energy**, turn on:
- **Prevent automatic sleeping when the display is off**
- **Start up automatically after a power failure**

Also turn on **automatic login** in **System Settings → Users & Groups**, so Caddy starts again after a restart.

## Raspberry Pi or other Debian/Ubuntu machine

```bash
curl -fsSL https://raw.githubusercontent.com/finvaultapp/finvault/main/deploy/site/install-pi.sh | bash
```

This works the same way. It uses `/var/www/finvault-site`, a systemd service and a nightly systemd timer. To update right away, run `sudo finvault-update-site`.

## Put it on the internet with Cloudflare Tunnel

**Quick test without a domain.** This prints a temporary `https://….trycloudflare.com` link that lasts until you stop it:

```bash
cloudflared tunnel --url http://localhost:8080
```

**Permanent, on your own domain** (the domain must be on Cloudflare):

1. In the Cloudflare dashboard, open **Zero Trust → Networks → Tunnels → Create a tunnel** and choose **Cloudflared**.
2. Pick your system: **macOS** for the Mac mini, or **Debian, arm64** for a Pi. Run the install command it shows (`sudo cloudflared service install <token>`). The tunnel then starts on its own at boot.
3. Under **Public hostnames**, add your hostname (for example `finvault.example.ca`) with service **HTTP** and URL `localhost:8080`.
