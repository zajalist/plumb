#!/usr/bin/env bash
# Bring up the plumb mask-inference server on a fresh Vultr GPU instance (Ubuntu 22.04 + NVIDIA).
# Usage:  bash bootstrap.sh
# Prints the bearer token at the end — copy it (and the instance's public IP) into the repo's
# local .vultr_token / .vultr_url. DESTROY THE INSTANCE WHEN DONE (see README — it bills hourly).
set -euo pipefail

cd "$(dirname "$0")"

# 1. System deps
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

# Vultr Ubuntu images ship with ufw active allowing only SSH (22) — open our port too,
# otherwise the box is unreachable on 8001 even with the Vultr edge firewall rule in place.
sudo ufw allow 8001/tcp 2>/dev/null || true

# 2. Python env
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip

# 3. GPU torch first (CUDA 12.1 wheel; change cu121 to match the instance's driver if needed)
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 4. The rest
pip install -r requirements.txt

# 5. Token + launch
TOKEN="${VULTR_TOKEN:-$(openssl rand -hex 16)}"
echo
echo "=================================================================="
echo " VULTR_TOKEN = $TOKEN"
echo " → put this in the repo's  .vultr_token  file"
echo " → put  http://<THIS_INSTANCE_PUBLIC_IP>:8001  in  .vultr_url"
echo "=================================================================="
echo
echo "Open port 8001 in the Vultr firewall, then the server starts below."
echo "First request per model downloads weights (slow); subsequent calls are warm."
echo

VULTR_TOKEN="$TOKEN" exec .venv/bin/uvicorn serve:app --host 0.0.0.0 --port 8001
