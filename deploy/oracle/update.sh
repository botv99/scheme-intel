#!/usr/bin/env bash
# ==============================================================================
# Scheme-Intel 24/7 Gateway Quick Update Script
# Pulls latest commits from git main branch and restarts the service
# ==============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${APP_DIR}"

echo -e "${CYAN}[*] Pulling latest updates from git main branch...${NC}"
git pull origin main

echo -e "${YELLOW}[*] Rebuilding container image...${NC}"
sudo docker compose build

echo -e "${YELLOW}[*] Restarting Scheme-Intel Gateway...${NC}"
sudo docker compose up -d

echo -e "${GREEN}[+] Update complete! Service status:${NC}"
sudo docker compose ps

echo -e "\n${CYAN}To view live logs:${NC} sudo docker compose logs -f gateway"
