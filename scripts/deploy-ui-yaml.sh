#!/usr/bin/env bash
# Copy the plugin's UI job descriptor into Pioreactor's plugin scan path.
# Run this on every unit that will run the job - each Pioreactor serves its
# own descriptors from its own disk; nothing copies them between units.
set -euo pipefail

# $HOME below decides where the descriptor lands. Under sudo that is /root,
# and the deploy would "succeed" into a directory Pioreactor never scans.
if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as the pioreactor user, not root/sudo - the descriptor must land in that user's \$HOME/.pioreactor." >&2
    exit 1
fi

PLUGIN=$(/opt/pioreactor/venv/bin/python -c "import pioreactor_electropioreactor_plugin, os; print(os.path.dirname(pioreactor_electropioreactor_plugin.__file__))")
# Same resolution order as patch-config-ini.py, so both steps of the install
# target one dot-directory rather than two.
DOT="${DOT_PIOREACTOR:-$HOME/.pioreactor}"
TARGET_DIR="$DOT/plugins/ui/jobs"
TARGET="$TARGET_DIR/20_electropioreactor.yaml"

mkdir -p "$TARGET_DIR"
cp "$PLUGIN/ui/contrib/jobs/electropioreactor.yaml" "$TARGET"
echo "Deployed: $TARGET"
