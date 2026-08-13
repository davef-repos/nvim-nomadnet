-- nvim-nomadnet plugin spec for lazy.nvim / LazyVim
--
-- Installs from the local source directory at ~/src/nvim-nomadnet.
-- nomadnet_core is available as a git submodule at ~/src/nvim-nomadnet/nomadnet_core.
-- The Python rplugin (nva.py) will be loaded via pynvim.
--
-- Usage:
--   Copy this file to ~/.config/nvim/lua/plugins/nvim-nomadnet.lua
--
-- Requires:
--   The following in init.lua BEFORE bootstrap lazy.nvim:
--     vim.g.python3_host_prog = "~/src/nvim-nomadnet/.venv/bin/python3"
--
-- Updating:
--   Since lazy.nvim treats dir= plugins as local, it won't auto-update
--   the git repo or submodules. To update manually:
--     1. cd ~/src/nvim-nomadnet && git pull
--     2. git submodule update --remote nomadnet_core
--     3. nvim --headless "+Lazy build nvim-nomadnet" +qa

local plugin_root = vim.fn.expand("~/src/nvim-nomadnet")

return {
  {
    dir = plugin_root,
    name = "nvim-nomadnet",
    opts = {
      configdir = nil,      -- nil = ~/.nomadnetwork
      rnsconfigdir = nil,   -- nil = ~/.reticulum
      verbose = false,
    },
    config = function(_, opts)
      require("nvim-nomadnet").setup(opts)
    end,
    -- Don't lazy-load; commands available immediately
    lazy = false,
    -- Keymaps are registered in lua/nvim-nomadnet/init.lua setup()
    -- Build step: create venv with all deps, symlink rplugin
    build = function()
      -- 0. Ensure git submodules are up to date
      vim.fn.system({ "git", "-C", plugin_root, "submodule", "update", "--init", "--recursive" })
      if vim.v.shell_error ~= 0 then
        vim.notify("nvim-nomadnet: git submodule update failed — check " .. plugin_root, vim.log.levels.WARN)
      end

      local venv_python = plugin_root .. "/.venv/bin/python3"

      -- 1. Create venv if missing
      if vim.fn.executable(venv_python) == 0 then
        vim.notify("nvim-nomadnet: creating Python venv...", vim.log.levels.INFO)
        vim.fn.system({ "python3", "-m", "venv", plugin_root .. "/.venv" })
        if vim.v.shell_error ~= 0 then
          vim.notify("nvim-nomadnet: venv creation failed", vim.log.levels.ERROR)
          return
        end
      end

      -- 2. Install dependencies into venv
      vim.notify("nvim-nomadnet: installing pip deps...", vim.log.levels.INFO)
      vim.fn.system({ venv_python, "-m", "pip", "install", "--quiet", "pynvim", "rns", "lxmf" })

      -- 3. Install nomadnet-core from local source
      local core_dir = plugin_root .. "/nomadnet_core"
      if vim.fn.isdirectory(core_dir) == 1 then
        vim.fn.system({ venv_python, "-m", "pip", "install", "--quiet", "-e", core_dir })
      end

      -- 4. Symlink rplugin into Neovim config
      local rplugin_dir = vim.fn.stdpath("config") .. "/rplugin/python3"
      vim.fn.mkdir(rplugin_dir, "p")
      vim.fn.system({ "ln", "-sf", plugin_root .. "/python/nva.py", rplugin_dir .. "/nva.py" })

      -- 5. Update remote plugins
      vim.fn.execute("UpdateRemotePlugins")

      vim.notify("nvim-nomadnet: setup complete. Restart Neovim.", vim.log.levels.INFO)
    end,
  },
}
