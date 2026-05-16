# Sift · self-host guide

Run your own Sift instance. Your data stays on your server; no third-party touches it except the LLM provider you choose.

## What you need

- A Linux VPS (1 vCPU / 1 GB RAM is enough for a single user; 2 GB recommended)
- A domain name with an A record pointing at the VPS
- An LLM API key (DeepSeek / SiliconFlow / OpenAI / etc.)
- Docker + Docker Compose plugin

## One-shot install

```bash
curl -fsSL https://raw.githubusercontent.com/HuanNan520/sift/main/install.sh | sudo bash
```

The script will:

1. Verify Docker is installed (offer to install it on Ubuntu/Debian)
2. Clone the repo into `/opt/sift`
3. Walk you through `.env` (domain, LLM URL, API key, admin email)
4. Generate a strong `JWT_SECRET` automatically
5. `docker compose up -d`
6. Wait for `/api/version` to respond

## Manual install

```bash
git clone https://github.com/HuanNan520/sift.git /opt/sift
cd /opt/sift
cp .env.example .env
$EDITOR .env            # fill in SIFT_DOMAIN, LLM_API_KEY, JWT_SECRET, ADMIN_EMAILS
docker compose up -d
docker compose logs -f sift-api
```

## After it is running

1. **DNS**: point an A record at the VPS public IP. Caddy will auto-issue a Let's Encrypt cert the first time the domain resolves.

2. **Verify**:
   ```bash
   curl https://YOUR_DOMAIN/api/version
   # → {"api_version":"0.7.1", …}
   ```

3. **Desktop APP**: download [Sift Desktop](https://github.com/HuanNan520/sift/releases) and during onboarding pick "I have my own Sift server", fill in your domain, then register.

4. **First admin**: register the email you put in `ADMIN_EMAILS` so `/api/admin/*` works.

## Updates

```bash
cd /opt/sift
sudo git pull
sudo docker compose up -d --build
```

The data volume persists across rebuilds.

## Backups

The volume `sift-data` lives at `/var/lib/docker/volumes/sift_sift-data/`. To copy out:

```bash
sudo docker compose exec sift-api tar czf /tmp/sift-backup.tgz /data
sudo docker cp sift-api:/tmp/sift-backup.tgz ./sift-backup-$(date +%F).tgz
```

Restore by unpacking the same tarball back into `/data` while `sift-api` is stopped.

## Email verification (optional)

To send real verification emails instead of the dev-mode stdout fallback, set in `.env`:

```
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=465
SMTP_USER=noreply@your-domain.com
SMTP_PASS=app-password
SMTP_FROM=Sift <noreply@your-domain.com>
EMAIL_VERIFY_REQUIRED=true    # optional: block login until verified
```

Restart: `sudo docker compose restart sift-api`.

## Invite-only mode

To require an invite code on registration:

```
INVITE_REQUIRED=true
```

Then as admin generate codes:

```bash
TOKEN=$(curl -s -X POST https://YOUR_DOMAIN/api/auth/login \
  -d 'email=ADMIN@example.com' -d 'password=YOURPASS' | jq -r .access_token)

curl -X POST https://YOUR_DOMAIN/api/admin/invite/generate \
  -d 'count=10' -d 'note=alpha' \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/api/version` returns 502 | `docker compose logs sift-api` — usually JWT_SECRET unset or LLM key wrong format |
| Caddy never gets a cert | DNS not propagated yet; wait 5-10 min then `docker compose restart caddy` |
| Verify email not arriving | Check `docker compose logs sift-api | grep dev mode` — if dev mode is logged, SMTP creds are missing |
| Rate-limit hit during testing | Per-IP 3/min on register, 5/min on login. Restart container to clear the in-memory bucket |

## Project links

- Source: <https://github.com/HuanNan520/sift>
- Issues: <https://github.com/HuanNan520/sift/issues>
- Discussions: <https://github.com/HuanNan520/sift/discussions>
