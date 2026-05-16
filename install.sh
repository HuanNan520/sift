#!/bin/bash
# Sift · self-host one-shot installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/HuanNan520/sift/main/install.sh | bash
#   OR
#   ./install.sh
#
# What it does:
#   1. Verify docker + docker compose are installed (offer to install if missing on Ubuntu/Debian)
#   2. Clone HuanNan520/sift into /opt/sift (or the directory you pick)
#   3. Walk you through filling .env (domain, LLM key, JWT secret)
#   4. docker compose up -d
#   5. Verify /api/version responds within 60s

set -euo pipefail

REPO_URL="https://github.com/HuanNan520/sift.git"
INSTALL_DIR="${SIFT_INSTALL_DIR:-/opt/sift}"
NEED_SUDO=""
if [[ $EUID -ne 0 ]] && command -v sudo >/dev/null; then
    NEED_SUDO="sudo"
fi

note() { printf '\033[1;36m▸\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*" >&2; exit 1; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$*"; }

note "Sift self-host installer"

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
    warn "Docker not found"
    if [[ -f /etc/os-release ]] && grep -qE 'ubuntu|debian' /etc/os-release; then
        read -rp "Install Docker via the official convenience script? [y/N] " yn
        if [[ "$yn" =~ ^[Yy]$ ]]; then
            curl -fsSL https://get.docker.com | $NEED_SUDO sh
        else
            fail "Aborting — please install Docker manually then re-run."
        fi
    else
        fail "Unsupported OS for auto Docker install. Install Docker manually then re-run."
    fi
fi
ok "Docker present: $(docker --version)"

if ! docker compose version >/dev/null 2>&1; then
    fail "docker compose plugin missing — install docker-compose-plugin and re-run."
fi
ok "Compose plugin present"

# 2. Clone
if [[ ! -d "$INSTALL_DIR" ]]; then
    note "Cloning $REPO_URL into $INSTALL_DIR"
    $NEED_SUDO git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# 3. .env
if [[ ! -f .env ]]; then
    note "Creating .env from .env.example"
    $NEED_SUDO cp .env.example .env
    read -rp "Your domain (e.g. sift.example.com): " D
    read -rp "LLM API base URL [https://api.deepseek.com/v1/chat/completions]: " U
    U="${U:-https://api.deepseek.com/v1/chat/completions}"
    read -rsp "LLM API key (starts with sk-): " K; echo
    JWT_SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(64))" 2>/dev/null || openssl rand -base64 48)
    read -rp "Admin email (gets /api/admin/* access): " A

    $NEED_SUDO sed -i "s|^SIFT_DOMAIN=.*|SIFT_DOMAIN=$D|" .env
    $NEED_SUDO sed -i "s|^SIFT_BASE_URL=.*|SIFT_BASE_URL=https://$D|" .env
    $NEED_SUDO sed -i "s|^LLM_API_URL=.*|LLM_API_URL=$U|" .env
    $NEED_SUDO sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$K|" .env
    $NEED_SUDO sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env
    $NEED_SUDO sed -i "s|^ADMIN_EMAILS=.*|ADMIN_EMAILS=$A|" .env
    ok "Wrote .env"
else
    ok ".env exists, leaving it alone"
fi

# 4. Build + run
note "Building image…"
$NEED_SUDO docker compose build
note "Starting…"
$NEED_SUDO docker compose up -d

# 5. Wait for /api/version
note "Waiting for /api/version (up to 60s)…"
for i in {1..30}; do
    if $NEED_SUDO docker compose exec -T sift-api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/version', timeout=2)" >/dev/null 2>&1; then
        ok "Backend reachable!"
        break
    fi
    sleep 2
done

DOMAIN=$(grep -E '^SIFT_DOMAIN=' .env | cut -d= -f2)
ADMIN=$(grep -E '^ADMIN_EMAILS=' .env | cut -d= -f2)

cat <<EOF

────────────────────────────────────────
✓ Sift is up
  Domain:        https://$DOMAIN
  Local URL:     http://$(hostname -I | awk '{print $1}'):80
  Admin email:   $ADMIN

Next steps:
  1. Point a DNS A record at this host so Caddy can issue HTTPS.
  2. Visit https://$DOMAIN/api/version once DNS propagates.
  3. Download the Sift desktop APP and pick "I have my own Sift server"
     during onboarding, fill in https://$DOMAIN, register with $ADMIN.
  4. Tail logs anytime: $NEED_SUDO docker compose logs -f sift-api

Update later: cd $INSTALL_DIR && $NEED_SUDO git pull && $NEED_SUDO docker compose up -d --build
────────────────────────────────────────
EOF
