#!/bin/bash
# install.sh — Install nvim-nomadnet plugin into Neovim (LazyVim)
# Usage: bash install.sh

set -e

PLUGIN_SRC="$(cd "$(dirname "$0")" && pwd)"
NVIM_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/nvim"

echo "=== nvim-nomadnet Installer ==="
echo ""

# 0. Ensure git submodules are initialized
echo "→ Initializing git submodules..."
git -C "$PLUGIN_SRC" submodule update --init --recursive
echo "  ✓ submodules up to date"

# 1. Create Python venv with all dependencies
echo "→ Setting up Python venv..."
VENV_PYTHON="$PLUGIN_SRC/.venv/bin/python3"
if [ ! -f "$VENV_PYTHON" ]; then
  python3 -m venv "$PLUGIN_SRC/.venv"
  echo "  ✓ venv created"
else
  echo "  ✓ venv already exists"
fi

# Install deps
echo "→ Installing Python dependencies..."
"$VENV_PYTHON" -m pip install --quiet pynvim rns lxmf
echo "  ✓ pynvim, rns, lxmf installed"

# Install nomadnet-core from local source
CORE_DIR="$PLUGIN_SRC/nomadnet_core"
if [ -d "$CORE_DIR" ]; then
  "$VENV_PYTHON" -m pip install --quiet -e "$CORE_DIR"
  echo "  ✓ nomadnet-core installed"
fi

# 2. Configure Neovim Python provider
echo "→ Configuring Neovim Python provider..."
mkdir -p "$NVIM_CONFIG/lua/config"
cat > "$NVIM_CONFIG/lua/config/nomadnet-python.lua" << PYEOF
-- Configure Neovim's Python provider for nvim-nomadnet
-- This MUST be sourced before lazy.nvim is loaded.
local plugin_venv = vim.fn.expand("$PLUGIN_SRC/.venv/bin/python3")
if vim.fn.executable(plugin_venv) == 1 then
  vim.g.python3_host_prog = plugin_venv
end
PYEOF
echo "  ✓ Python provider config written"

# 3. Install lazy.nvim plugin spec
echo "→ Installing lazy.nvim plugin spec..."
cp "$PLUGIN_SRC/lazy-setup.lua" "$NVIM_CONFIG/lua/plugins/nvim-nomadnet.lua"
echo "  ✓ Plugin spec installed"

# 4. Symlink Python rplugin
echo "→ Registering Python rplugin..."
mkdir -p "$NVIM_CONFIG/rplugin/python3"
ln -sf "$PLUGIN_SRC/python/nva.py" "$NVIM_CONFIG/rplugin/python3/nva.py"
echo "  ✓ rplugin symlinked"

# 5. Ensure init.lua loads Python provider first
if ! grep -q "nomadnet-python" "$NVIM_CONFIG/init.lua" 2>/dev/null; then
  # Insert after shebang/preamble, before lazy bootstrap
  sed -i '1s/^/require("config.nomadnet-python")\n/' "$NVIM_CONFIG/init.lua"
  echo "  ✓ init.lua updated to load Python provider first"
fi

# 6. Update remote plugins
echo "→ Running UpdateRemotePlugins..."
nvim --headless \
  -c "lua vim.g.python3_host_prog = vim.fn.expand('$PLUGIN_SRC/.venv/bin/python3')" \
  -c "UpdateRemotePlugins" \
  -c "qall" 2>&1
echo "  ✓ rplugin manifest generated"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Next steps:"
echo "  1. Restart Neovim"
echo "  2. Run :NvaStart"
echo "  3. Run :NvaConversations"
echo "  4. Or use keymaps: <leader>Nc, <leader>Nn, <leader>Nh, <leader>Nd, <leader>Ns"
echo ""
