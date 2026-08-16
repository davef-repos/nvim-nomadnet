<p align="center">
  <img src="https://raw.githubusercontent.com/markqvist/NomadNet/master/docs/_static/images/logo.png" alt="NomadNet" width="200"/>
</p>

# nvim-nomadnet

> A Neovim plugin for [NomadNet](https://github.com/markqvist/NomadNet) — a decentralized, encrypted mesh communication platform built on [Reticulum](https://github.com/markqvist/Reticulum) and [LXMF](https://github.com/markqvist/LXMF).

**nvim-nomadnet** brings the full NomadNet experience into Neovim, allowing you to send encrypted messages, browse network peers, fetch node pages, participate in RRC channels, and manage your peer directory — all from within your editor.

## Features

- **Encrypted Conversations** — View, read, and send encrypted LXMF messages directly to any peer on the mesh
- **Network Browser** — Browse announces from nodes, peers, and propagation nodes
- **Node Page Browser** — Fetch and browse HTML pages hosted on NomadNet nodes
- **RRC Channels** — Browse and participate in Request-Response Conversation chat channels
- **Peer Directory** — View, manage, and trust/untrust known peers
- **LXMF Sync** — Trigger message sync from configured propagation nodes
- **Statusline Integration** — Display NomadNet identity and status in your statusline
- **Low Dependencies** — Uses nomadnet-core, a minimal UI-agnostic protocol layer

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| [Neovim](https://neovim.io/) | ≥ 0.8 | With Python 3 provider (`:checkhealth provider.python`) |
| [Python 3](https://python.org/) | ≥ 3.8 | With `pynvim` |
| [Reticulum](https://github.com/markqvist/Reticulum) | ≥ 1.3.2 | Mesh networking stack |
| [LXMF](https://github.com/markqvist/LXMF) | ≥ 1.0.0 | Lightweight encrypted messaging |
| [nomadnet-core](https://github.com/markqvist/NomadNet) | — | Included as git submodule |

## Installation

### Option A: lazy.nvim (recommended for LazyVim)

<details>
<summary><strong>Install script (quick setup)</strong></summary>

```bash
# Clone the repo with submodules
git clone --recursive https://github.com/davef-repos/nvim-nomadnet

# Run the installer from the repo root
cd nvim-nomadnet
bash install.sh
```

This will:
1. Initialize the `nomadnet_core` git submodule
2. Create a Python virtualenv with all dependencies
3. Install `pynvim`, `rns`, and `lxmf` into the venv
4. Install `nomadnet-core` from local source (editable mode)
5. Register the rplugin and generate the remote plugin manifest
6. Copy the lazy.nvim plugin spec to your config

</details>

<details>
<summary><strong>Manual lazy.nvim setup</strong></summary>

lazy.nvim will clone the repo automatically. Place the following spec in your plugins directory (e.g. `~/.config/nvim/lua/plugins/nvim-nomadnet.lua`):

```lua
-- nvim-nomadnet plugin spec for lazy.nvim / LazyVim
return {
  {
    name = "nvim-nomadnet",
    url = "davef-repos/nvim-nomadnet",
    opts = {
      configdir = nil,      -- nil = ~/.nomadnetwork
      rnsconfigdir = nil,   -- nil = ~/.reticulum
      verbose = false,
    },
    config = function(_, opts)
      require("nvim-nomadnet").setup(opts)
    end,
    lazy = false,
    build = function()
      local root = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
      -- ... (see lazy-setup.lua for full build function)
    end,
  },
}
```

</details>

<details>
<summary><strong>Python provider configuration</strong></summary>

Before `lazy.nvim` bootstraps, your `init.lua` must set the Python host:

```lua
-- ~/.config/nvim/init.lua
-- MUST be before lazy bootstrap:

require("config.nomadnet-python")
require("config.lazy")
```

Where `~/.config/nvim/lua/config/nomadnet-python.lua` contains:

```lua
local plugin_root = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
local plugin_venv = plugin_root .. "/.venv/bin/python3"
if vim.fn.executable(plugin_venv) == 1 then
  vim.g.python3_host_prog = plugin_venv
end
```

</details>

### Option B: vim-plug

```vim
Plug 'davef-repos/nvim-nomadnet', { 'do': 'bash install.sh' }
```

### Option C: Manual (packpath)

```bash
# Clone with submodules
git clone --recursive https://github.com/davef-repos/nvim-nomadnet \
  ~/.local/share/nvim/site/pack/plugins/start/nvim-nomadnet

# Run the installer
cd ~/.local/share/nvim/site/pack/plugins/start/nvim-nomadnet
bash install.sh
```

## Quick Start

1. **Start Neovim** and run:

```vim
:NvaStart
```

This loads or creates your NomadNet identity, initializes Reticulum, and starts the LXMF router.

2. **Open the conversation list**:

```vim
:NvaConversations
```
or press `<leader>Nc`.

3. **Browse the network** for peers and nodes:

```vim
:NvaNetwork
```
or press `<leader>Nn`.

4. **Browse RRC channels**:

```vim
:NvaChannels
```
or press `<leader>Nh`.

5. **Send a message**: Navigate to a conversation or peer identity, then:

```vim
:NvaSendMessage <destination_hash> "Your message"
```

## Commands

### Core

| Command | Description |
|---------|-------------|
| `:NvaStart [configdir] [rnsdir]` | Start NomadNet — loads/creates identity, initializes Reticulum and LXMF |
| `:NvaQuit` | Gracefully stop the NomadNet core |
| `:NvaRefresh` | Redraw the currently active nomadnet buffer |
| `:NvaSync` | Trigger LXMF message sync from configured propagation node |

### Views

| Command | Description |
|---------|-------------|
| `:NvaConversations` | Open the encrypted conversation list |
| `:NvaNetwork` | Open the network announce browser |
| `:NvaChannels` | Open the RRC (channels) list |
| `:NvaDirectory` | Open the peer trust directory |

## Keybindings

### NomadNet Buffers

| Key | Action | Context |
|-----|--------|---------|
| `<CR>` | Open / select item under cursor | All views |
| `<Tab>` | Cycle views (conv → network → channels → directory) | All views |
| `r` | Refresh current view | All views |
| `q` | Close current buffer | All views |
| `?` | Toggle help overlay | All views |
| `d` | Delete selected conversation | Conversation list |
| `c` | Compose new message to selected peer | Conversation list / Network |
| `u` | Fetch page at URL under cursor | Network browser |
| `n` | Sync messages from propagation node | Conversation list |
| `m` | Mark selected conversation as read | Conversation list |
| `<C-s>` | Send message | Compose buffer |
| `Y` | Yank identity hash under cursor | All views |

### Leader Shortcuts

These are defined in the `setup()` function. The default prefix is `<leader>N` (capital N).

| Shortcut | Command |
|----------|---------|
| `<leader>Nc` | `:NvaConversations` |
| `<leader>Nn` | `:NvaNetwork` |
| `<leader>Nh` | `:NvaChannels` |
| `<leader>Nd` | `:NvaDirectory` |
| `<leader>Ns` | `:NvaSync` |

To customize the prefix, pass `map_prefix` in setup:

```lua
require("nvim-nomadnet").setup({
  map_prefix = "<leader>M",  -- default is <leader>N
})
```

## Configuration

All options and their defaults:

```lua
require("nvim-nomadnet").setup({
  configdir = nil,      -- Path to NomadNet config (nil = ~/.nomadnetwork)
  rnsconfigdir = nil,   -- Path to RNS config (nil = ~/.reticulum)
  map_prefix = "<LocalLeader>n",  -- Prefix for nomadnet buffer keymaps
  detail_width = 80,    -- Default width for detail/info windows
  verbose = false,      -- Enable verbose RNS logging
})
```

## API

### Lua Functions

| Function | Description |
|----------|-------------|
| `require("nvim-nomadnet").setup(opts)` | Initialize the plugin with options |
| `require("nvim-nomadnet").start()` | Start NomadNet core (`:NvaStart`) |
| `require("nvim-nomadnet").stop()` | Stop NomadNet core |
| `require("nvim-nomadnet").refresh()` | Redraw current view |
| `require("nvim-nomadnet").cycle_view()` | Cycle through views |
| `require("nvim-nomadnet").open_conversation()` | Open conversation list |
| `require("nvim-nomadnet").open_announce()` | Open network browser |
| `require("nvim-nomadnet").open_channel()` | Open RRC channel list |
| `require("nvim-nomadnet").open_directory()` | Open peer directory |
| `require("nvim-nomadnet").statusline()` | Returns statusline string |

### Statusline Integration

Add NomadNet identity to your statusline:

```lua
-- In your statusline configuration:
set statusline+=%{%v:lua.require('nvim-nomadnet').statusline()%}
```

## Architecture

```
┌────────────────────────────────────────────────────────┐
│                     Neovim                             │
│  ┌──────────────┐       ┌──────────────────────────┐  │
│  │ Lua Plugin    │◄─────►│ Python Backend (nva.py)  │  │
│  │ init.lua      │ RPC   │ @pynvim.plugin           │  │
│  │               │       │                          │  │
│  │ • Keymaps     │       │ • Conversation API       │  │
│  │ • Commands    │       │ • Network API            │  │
│  │ • Buffer mgmt │       │ • Directory API          │  │
│  │ • Rendering   │       │ • RRC API                │  │
│  └──────────────┘       └──────┬───────────────────┘  │
└────────────────────────────────┼──────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    nomadnet_core         │
                    │    (git submodule)       │
                    │                          │
                    │ • Conversation           │
                    │ • Directory              │
                    │ • Node                   │
                    │ • RRC                    │
                    │ • PageFetcher            │
                    │ • util                   │
                    └──────┬───────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         Reticulum       LXMF      HTTP/Node
         (mesh net)    (messages)   (pages)
```

### Layer Details

1. **Lua Plugin** (`lua/nvim-nomadnet/init.lua`)
   - Single-file entry point
   - Creates and manages Neovim buffers for each view
   - Registers commands (`:Nva*`) and keymaps
   - Renders structured data (tables, message threads, lists)
   - Communicates with the Python backend via `vim.fn.Nva*` RPC calls

2. **Python Backend** (`python/nva.py`)
   - `NomadNetAgent` class decorated with `@pynvim.plugin`
   - Exposes API functions (`NvaConversations`, `NvaSendMessage`, etc.)
   - Implements the `UIBackend` interface for `nomadnet_core`
   - Manages identity, announces, and network state

3. **Core Library** (`nomadnet_core/`)
   - Git submodule pointing to the [nomadnet-core](https://github.com/markqvist/NomadNet) project
   - UI-agnostic protocol and data-model layer
   - Handles Reticulum transport, LXMF message routing, RRC protocol, directory management

## Updating

### From lazy.nvim

```vim
:Lazy update nvim-nomadnet
```

lazy.nvim will automatically fetch the submodule.

### From a local clone

```bash
cd /path/to/nvim-nomadnet
git pull                              # Pull latest plugin changes
git submodule update --remote         # Pull latest nomadnet-core
nvim --headless "+Lazy build nvim-nomadnet" +qa
```

### Using the install script

```bash
cd /path/to/nvim-nomadnet
git pull
git submodule update --init --recursive
bash install.sh
```

## Troubleshooting

### "Python 3 provider is not available"

Ensure your Python virtualenv is set up:

```bash
cd /path/to/nvim-nomadnet
python3 -m venv .venv
.venv/bin/pip install pynvim rns lxmf
.venv/bin/pip install -e nomadnet_core
```

Then configure the Python host in `init.lua`:

```lua
local plugin_root = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
vim.g.python3_host_prog = plugin_root .. "/.venv/bin/python3"
```

### "No commands available"

Run `:UpdateRemotePlugins` and restart Neovim. Ensure `python/nva.py` is symlinked to your rplugin directory:

```bash
ln -sf /path/to/nvim-nomadnet/python/nva.py \
      ~/.config/nvim/rplugin/python3/nva.py
```

### ":checkhealth" help

```vim
:checkhealth provider.python
:checkhealth nvim-nomadnet
```

### Logging

Enable verbose logging for debugging:

```lua
require("nvim-nomadnet").setup({
  verbose = true,
})
```

Check RNS logs at `~/.reticulum/logfile` and NomadNet logs at `~/.nomadnetwork/logfile`.

## Related Projects

- [NomadNet](https://github.com/markqvist/NomadNet) — The original NomadNet TUI application
- [Reticulum](https://github.com/markqvist/Reticulum) — Cryptography-based networking stack
- [LXMF](https://github.com/markqvist/LXMF) — Lightweight eXtensible Message Format
- [nomadnet-core](https://github.com/markqvist/NomadNet) — Reusable core library (git submodule)

## License

MIT — See [LICENSE](https://github.com/markqvist/NomadNet/blob/master/LICENSE) for details.

Built on the work of [Mark Qvist](https://github.com/markqvist) and the NomadNet / Reticulum community.
