#!/usr/bin/env bash
# CPU-only bring-up of the plumb mask-inference server — for when Cloud GPU access isn't
# enabled yet (Vultr gates GPU products behind a support request). Identical to bootstrap.sh
# except it installs the CPU torch wheel and runs the models on CPU (VULTR_DEVICE=cpu).
#
# Works on any regular Vultr instance (e.g. a vhf high-frequency plan), no GPU needed.
# segformer / CLIPSeg / Depth-Anything are usable on CPU (seconds/image); SAM is slow
# (tens of seconds) — fine for a few demo assets, swap to the GPU box for real throughput.
#
# Usage:  bash bootstrap_cpu.sh
set -euo pipefail

cd "$(dirname "$0")"

sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip

# Vultr Ubuntu images ship with ufw active allowing only SSH (22) — open our port too,
# otherwise the box is unreachable on 8001 even with the Vultr edge firewall rule in place.
sudo ufw allow 8001/tcp 2>/dev/null || true

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip

# CPU torch + torchvision TOGETHER from the same index — installing torch alone lets timm
# pull a mismatched torchvision, which breaks `transformers` with
# "operator torchvision::nms does not exist".
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

pip install -r requirements.txt

TOKEN="${VULTR_TOKEN:-$(openssl rand -hex 16)}"
echo
echo "=================================================================="
echo " VULTR_TOKEN = $TOKEN"
echo " → put this in the repo's  .vultr_token  file"
echo " → put  http://<THIS_INSTANCE_PUBLIC_IP>:8001  in  .vultr_url"
echo " RUNNING ON CPU — first request per model downloads weights (slow),"
echo " and SAM inference is slow on CPU. Subsequent calls are warm."
echo "=================================================================="
echo

VULTR_TOKEN="$TOKEN" VULTR_DEVICE="cpu" exec .venv/bin/uvicorn serve:app --host 0.0.0.0 --port 8001
