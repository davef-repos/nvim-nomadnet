# Contributing to nvim-nomadnet

> **⚠️ Vibe-coded alpha software** — This is an experimental, rapidly-evolving project built with AI assistance. Things may break, APIs may change without notice, and some features may not work correctly yet. Keep this in mind when filing issues or submitting PRs.

Thank you for your interest in contributing! This plugin is part of the broader NomadNet ecosystem, and contributions are welcome at every level.

## Code of Conduct

Be respectful, constructive, and kind. This project follows the same community standards as the NomadNet / Reticulum project.

## How to Contribute

### Reporting Issues

- Search [existing issues](https://github.com/yourusername/nvim-nomadnet/issues) first
- Include your Neovim version (`:version`), Python version, and OS
- Include relevant logs (`~/.reticulum/logfile`, `~/.nomadnetwork/logfile`)
- Include steps to reproduce

### Feature Requests

Open an issue describing:

1. What you want to achieve
2. Why it would be useful
3. Any relevant NomadNet/RNs/LXMF features it relies on

### Pull Requests

1. **Fork** the repo (both `nvim-nomadnet` and `nomadnet-core` if changes touch the core)
2. **Create a feature branch** from `main`
3. **Make your changes**
4. **Test** — Ensure `:NvaStart` and `:NvaConversations` work
5. **Commit** with clear messages
6. **Open a PR**

#### PR Guidelines

- Keep changes focused — one feature/fix per PR
- If you change the Lua plugin layer, update `doc/nvim-nomadnet.txt`
- If you change the Python backend, update `python/nva.py` signatures
- If you change `nomadnet_core`, submit a separate PR to that repo

## Development Setup

```bash
# Clone with submodules
git clone --recursive https://github.com/yourusername/nvim-nomadnet
cd nvim-nomadnet

# Set up the Python environment
python3 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install pynvim rns lxmf
.venv/bin/pip install -e nomadnet_core

# Symlink the rplugin
ln -sf "$PWD/python/nva.py" ~/.config/nvim/rplugin/python3/nva.py

# Generate remote plugin manifest
nvim --headless -c "lua vim.g.python3_host_prog='$PWD/.venv/bin/python3'" \
  -c "UpdateRemotePlugins" -c "qall"

# Restart Neovim and test
nvim +NvaStart
```

## Project Structure

```
nvim-nomadnet/
├── doc/
│   ├── nvim-nomadnet.txt   # Vim help file
│   └── rplugin.txt         # rplugin registration notes
├── lua/
│   ├── nvim-nomadnet/
│   │   └── init.lua        # Main Lua plugin (single file)
│   └── nvim-nomadnet.lua   # Re-export module
├── plugin/
│   └── nvim-nomadnet.vim   # Vimscript plugin loader
├── python/
│   ├── nva.py              # Python pynvim backend
│   └── provider.lua        # Python host config sample
├── install.sh              # Automated installer
├── lazy-setup.lua          # lazy.nvim plugin spec
├── rplugin.vim             # rplugin manifest notes
├── nomadnet_core/          # Git submodule
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

## Architecture Overview

```
User Input → Lua Plugin (keymaps/commands)
               │
               │ vim.fn.Nva*(...) RPC calls
               ▼
          Python Backend (nva.py)
               │
               │ imports
               ▼
          nomadnet_core (submodule)
               │
               ├── Reticulum (transport)
               ├── LXMF (messages)
               └── HTTP/Node (page fetcher)
```

## Style Guide

### Lua

- 2-space indentation
- `snake_case` for functions and variables
- `PascalCase` for module-level tables
- Document public API with `---` doc comments

### Python

- Follow PEP 8 (4-space indentation)
- Type hints for function signatures
- Document `@pynvim.command` and `@pynvim.function` methods clearly

### Commits

Use conventional commit prefixes:

```
feat: add channel browser sorting
fix: handle empty conversation list gracefully
docs: update README with new keybindings
refactor: extract buffer rendering into helper functions
chore: update submodule to latest nomadnet-core
```

## Testing

Currently, testing is manual:

1. Start Neovim with the plugin loaded
2. Run `:NvaStart` and verify identity creation
3. Test each view: `:NvaConversations`, `:NvaNetwork`, `:NvaChannels`, `:NvaDirectory`
4. Test sync: `:NvaSync`
5. Verify all keybindings work in each view
6. Check `:checkhealth provider.python`

Automated testing infrastructure is planned.

## Questions?

Open a [discussion](https://github.com/yourusername/nvim-nomadnet/discussions) or issue.
