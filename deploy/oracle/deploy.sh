#!/usr/bin/env bash
# ==============================================================================
# Scheme-Intel 24/7 Telegram Conversational Gateway Deploy Script
# Optimized for: Oracle Cloud Infrastructure (OCI) Always Free Ubuntu VM
# Also works on: Ubuntu 22.04 / 24.04 (AMD64 / ARM64 Ampere A1)
# ==============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}================================================================${NC}"
echo -e "${CYAN}  Scheme-Intel: 24/7 Cloud VM Telegram Gateway Provisioning     ${NC}"
echo -e "${CYAN}================================================================${NC}"

# 1. Determine target directory
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${APP_DIR}"
echo -e "${GREEN}[+] Operating directory:${NC} ${APP_DIR}"

# 2. Install Docker & Compose plugin if not already installed
if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}[*] Installing Docker and Docker Compose plugin...${NC}"
    sudo apt-get update -y
    sudo apt-get install -y ca-certificates curl gnupg lsb-release
    
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    ARCH="$(dpkg --print-architecture)"
    CODENAME="$(lsb_release -cs)"
    echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${CODENAME} stable" | \
        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    sudo systemctl enable docker
    sudo systemctl start docker

    # Add current user to docker group
    if [ -n "${USER:-}" ] && [ "${USER}" != "root" ]; then
        sudo usermod -aG docker "${USER}"
        echo -e "${GREEN}[+] Added ${USER} to docker group.${NC}"
    fi
else
    echo -e "${GREEN}[+] Docker and Docker Compose are already installed.${NC}"
fi

# 3. Create persistent directories and set permissions
echo -e "${YELLOW}[*] Configuring persistent storage directories...${NC}"
mkdir -p "${APP_DIR}/data/intelligence" "${APP_DIR}/logs"
chmod -R 775 "${APP_DIR}/data" "${APP_DIR}/logs"

# 4. Check for .env file
if [ ! -f "${APP_DIR}/.env" ]; then
    echo -e "${YELLOW}[!] .env file not found. Initializing from .env.example...${NC}"
    cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    echo -e "${RED}[!] ACTION REQUIRED: Please edit .env now with your credentials:${NC}"
    echo -e "    nano ${APP_DIR}/.env"
    echo -e "    (Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)"
    echo -e "    Then re-run this deploy script."
    exit 1
fi

# Verify TELEGRAM_BOT_TOKEN is set in .env
if ! grep -q "^TELEGRAM_BOT_TOKEN=[0-9A-Za-z_:-]\+" "${APP_DIR}/.env" 2>/dev/null; then
    echo -e "${RED}[!] WARNING: TELEGRAM_BOT_TOKEN appears empty in ${APP_DIR}/.env${NC}"
    echo -e "    Please edit ${APP_DIR}/.env and set your bot token before starting."
    echo -e "    Command: nano ${APP_DIR}/.env"
fi

# 5. Build and launch containers via Docker Compose
echo -e "${YELLOW}[*] Building and starting scheme-intel gateway container...${NC}"
sudo docker compose -f "${APP_DIR}/docker-compose.yml" build
sudo docker compose -f "${APP_DIR}/docker-compose.yml" up -d

# 6. Configure systemd service for boot autostart
echo -e "${YELLOW}[*] Registering systemd autostart service...${NC}"
SERVICE_FILE="/etc/systemd/system/scheme-intel.service"
sudo cp "${APP_DIR}/deploy/scheme-intel.service" "${SERVICE_FILE}"
sudo sed -i "s|/home/ubuntu/scheme-intel|${APP_DIR}|g" "${SERVICE_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable scheme-intel.service

# 7. Health check verification
echo -e "${YELLOW}[*] Waiting 5 seconds for service initialization...${NC}"
sleep 5

echo -e "${YELLOW}[*] Running health check probe...${NC}"
if sudo docker compose -f "${APP_DIR}/docker-compose.yml" exec -T gateway python -m scheme_intel.delivery.service --health; then
    echo -e "${GREEN}================================================================${NC}"
    echo -e "${GREEN}  SUCCESS: Scheme-Intel 24/7 Gateway is active and healthy!     ${NC}"
    echo -e "${GREEN}================================================================${NC}"
else
    echo -e "${YELLOW}[!] Note: Initial health probe reported degraded or missing token.${NC}"
    echo -e "    Check logs with: sudo docker compose logs -f gateway"
fi

echo -e "\n${CYAN}Useful Operational Commands:${NC}"
echo -e "  View live logs:         sudo docker compose logs -f gateway"
echo -e "  Check container status: sudo docker compose ps"
echo -e "  Restart service:        sudo docker compose restart gateway"
echo -e "  Update & redeploy:      ${APP_DIR}/deploy/oracle/update.sh"
echo -e "  HTTP Health check:      curl http://localhost:8080/"
