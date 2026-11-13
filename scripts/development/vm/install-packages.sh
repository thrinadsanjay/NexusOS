#!/usr/bin/env bash
# Copy the built NexusOS packages into the disposable test VM and install them there.
#
#   scripts/development/vm/install-packages.sh [DEB_DIR] [--port 2222] [--user nexus]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEBS="$REPO_ROOT/build/debs"; PORT=2222; USER_NAME=nexus
while [ $# -gt 0 ]; do
    case "$1" in
        --port) PORT="$2"; shift 2 ;;
        --user) USER_NAME="$2"; shift 2 ;;
        *) DEBS="$(realpath "$1")"; shift ;;
    esac
done
SSH=(ssh -p "$PORT" -o StrictHostKeyChecking=accept-new "$USER_NAME@127.0.0.1")
"${SSH[@]}" "rm -rf ~/nexusos-debs && mkdir ~/nexusos-debs"
scp -P "$PORT" "$DEBS"/*.deb "$USER_NAME@127.0.0.1:nexusos-debs/"
"${SSH[@]}" "sudo apt-get update && sudo apt-get install -y ~/nexusos-debs/*.deb && nexus version && systemctl status nexusos-agent.socket --no-pager"
echo "Installed. Log in to the Plasma session in the VM window and start 'Nexus Command Center'."
