# nvim-nomadnet

A **Neovim plugin** for [NomadNet](https://github.com/markqvist/NomadNet) — a decentralized, encrypted mesh communication platform built on [Reticulum](https://github.com/markqvist/Reticulum) and [LXMF](https://github.com/markqvist/LXMF).

This plugin uses the `nomadnet_core` library (extracted as a reusable package) to provide a full NomadNet experience inside Neovim.

## Features

- **Conversations** — View, read, and send encrypted LXMF messages to peers
- **Network Browser** — Browse announces from nodes, peers, and propagation nodes on the mesh
- **Node Page Browser** — Fetch and view pages hosted on NomadNet nodes
- **RRC Channels** — Browse and read RRC (Request-Response Conversation) chat channels
- **Peer Directory** — View and manage known peers and their trust levels
- **LXMF Sync** — Trigger sync with propagation nodes to fetch queued messages

## Requirements

- Neovim ≥ 0.8 (with Python 3 provider)
- Python 3 with `pynvim` installed:
  ```bash
  pip install pynvim
  ```
- `nomadnet_core` (included as a git submodule at `nomadnet_core/`). Install from source:
  ```bash
  cd nomadnet_core
  pip install -e .
  ```
  Or via pip when published:
  ```bash
  pip install nomadnet-core
  ```

## Installation

### Using a plugin manager (lazy.nvim)

```lua
{
  dir = "~/src/NomadNet/nvim-nomadnet",  -- or a git URL
  config = function()
    require("nvim-nomadnet").setup({
      configdir = nil,      -- nil = ~/.nomadnetwork
      rnsconfigdir = nil,   -- nil = ~/.reticulum
      verbose = false,
    })
  end,
}
```

### Manual

```bash
# Clone or symlink the plugin directory
ln -s ~/src/NomadNet/nvim-nomadnet ~/.local/share/nvim/site/pack/plugins/start/nvim-nomadnet
```

Then in your `init.lua`:

```lua
require("nvim-nomadnet").setup()
```

## Usage

### Commands

| Command | Description |
|---------|-------------|
| `:NvaStart [configdir] [rnsdir]` | Start NomadNet core (loads/creates identity) |
| `:NvaConversations` | Open conversation list |
| `:NvaNetwork` | Open network announce browser |
| `:NvaChannels` | Open RRC channel list |
| `:NvaDirectory` | Open peer directory |
| `:NvaSync` | Trigger LXMF sync from propagation node |
| `:NvaRefresh` | Refresh current view |
| `:NvaQuit` | Stop NomadNet |

### Keybindings (in nomadnet buffers)

| Key | Action |
|-----|--------|
| `<CR>` | Open / select item under cursor |
| `r` | Refresh current view |
| `q` | Close current buffer / quit view |
| `d` | Delete conversation (in conversation list) |
| `c` | Compose message (in conversation view) |
| `u` | Fetch URL (in network view) |
| `<C-s>` | Send composed message (in compose buffer) |
| `n` | Sync messages (in conversation list) |
| `m` | Mark selected conversation as read |

### Leader key shortcuts

| Shortcut | Command |
|----------|---------|
| `<leader>Nc` | `:NvaConversations` |
| `<leader>Nn` | `:NvaNetwork` |
| `<leader>Nh` | `:NvaChannels` |
| `<leader>Nd` | `:NvaDirectory` |
| `<leader>Ns` | `:NvaSync` |

## Architecture

```
Neovim ←→ nvim-nomadnet (Lua) ←→ nva.py (Python RPC plugin) ←→ nomadnet_core (Python)
```

- **Lua layer** (`lua/nvim-nomadnet/init.lua`): Handles buffer management, keymaps, and user commands.
- **Python backend** (`python/nva.py`): A `pynvim` plugin that wraps `nomadnet_core` and exposes API functions (`NvaConversations`, `NvaSendMessage`, etc.).
- **Core library** (`nomadnet_core/`): The reusable, UI-agnostic protocol and data-model layer.

## License

Same as NomadNet — MIT License.
