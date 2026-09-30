# Hosting the landing site

The landing site in [`site/`](../../site) is plain static files: HTML, CSS, one script, images and fonts. There's no build step and it makes no third-party requests.

This guide puts it on a Raspberry Pi with [Caddy](https://caddyserver.com), and on the internet through a [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/). You don't need router port forwarding, your home IP isn't exposed, and HTTPS comes free.

> This is for the public landing page only. Keep the FinVault app itself private on your home network, and use something like Tailscale if you want to reach it away from home.

## 1. Install on the Pi

Run this on the Pi (Raspberry Pi OS or Debian, 64-bit):

```bash
curl -fsSL https://raw.githubusercontent.com/henilsarang/finvault/main/deploy/site/install-pi.sh | bash
```

It does four things:
- installs Caddy, git and rsync
- downloads only the `site/` folder from GitHub into `/var/www/finvault-site`
- serves it on port 8080, with security headers from [`Caddyfile`](Caddyfile)
- refreshes it from GitHub every night at 03:30

Check it at `http://<pi-address>:8080`. To publish a change right away:

```bash
sudo finvault-update-site
```

## 2. Put it on the internet

**Quick test without a domain.** This prints a temporary `https://….trycloudflare.com` link that lasts until you stop it:

```bash
cloudflared tunnel --url http://localhost:8080
```

**Permanent, on your own domain** (the domain must be on Cloudflare):

1. In the Cloudflare dashboard, open **Zero Trust → Networks → Tunnels → Create a tunnel** and choose **Cloudflared**.
2. Pick **Debian** and **arm64**, then run the install command it shows on the Pi. It installs `cloudflared` as a service that starts on boot.
3. Under **Public hostnames**, add your hostname (for example `finvault.example.ca`) with service **HTTP** and URL `localhost:8080`.

## On a Mac instead

The same Caddyfile works on macOS:

```bash
brew install caddy
sudo mkdir -p /var/www && sudo cp -R site /var/www/finvault-site
sudo caddy run --config deploy/site/Caddyfile
```

A Pi is the better home for the site because it's always on and uses very little power. If you do use a Mac, stop it from sleeping (System Settings → Energy).
