-- nvim-nomadnet plugin spec for lazy.nvim / LazyVim
--
-- How it works:
--   - If ~/src/nvim-nomadnet exists (development), uses that local copy
--   - Otherwise, lazy.nvim clones from the GitHub URL below (once set)
--
-- When ready for GitHub:
--   1. Push both repos to GitHub
--   2. Uncomment the `url` line below
--   3. Update .gitmodules to point to the GitHub URL
--
-- Requires:
--   The following in init.lua BEFORE bootstrap lazy.nvim:
--     vim.g.python3_host_prog = "~/src/nvim-nomadnet/.venv/bin/python3"

local plugin_root = vim.fn.expand("~/src/nvim-nomadnet")
local is_dev = vim.fn.isdirectory(plugin_root) == 1

return {
  {
    name = "nvim-nomadnet",
    -- url = "yourusername/nvim-nomadnet",  -- uncomment when on GitHub
    opts = {
      configdir = nil,      -- nil = ~/.nomadnetwork
      rnsconfigdir = nil,   -- nil = ~/.reticulum
      verbose = false,
    },
    config = function(_, opts)
      require("nvim-nomadnet").setup(opts)
    end,
    lazy = false,

    -- Local dev path fallback; ignored when url is set
    dir = is_dev and plugin_root or nil,

    build = function()
      local root
      if is_dev then
        root = plugin_root
        vim.fn.system({ "git", "-C", root, "submodule", "update", "--init", "--recursive" })
      else
        root = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
      end

      local venv_python = root .. "/.venv/bin/python3"

      if vim.fn.executable(venv_python) == 0 then
        vim.notify("nvim-nomadnet: creating Python venv...", vim.log.levels.INFO)
        vim.fn.system({ "python3", "-m", "venv", root .. "/.venv" })
        if vim.v.shell_error ~= 0 then
          vim.notify("nvim-nomadnet: venv creation failed", vim.log.levels.ERROR)
          return
        end
      end

      vim.notify("nvim-nomadnet: installing pip deps...", vim.log.levels.INFO)
      vim.fn.system({ venv_python, "-m", "pip", "install", "--quiet", "pynvim", "rns", "lxmf" })

      local core_dir = root .. "/nomadnet_core"
      if vim.fn.isdirectory(core_dir) == 1 then
        vim.fn.system({ venv_python, "-m", "pip", "install", "--quiet", "-e", core_dir })
      end

      local rplugin_dir = vim.fn.stdpath("config") .. "/rplugin/python3"
      vim.fn.mkdir(rplugin_dir, "p")
      vim.fn.system({ "ln", "-sf", root .. "/python/nva.py", rplugin_dir .. "/nva.py" })

      vim.fn.execute("UpdateRemotePlugins")
      vim.notify("nvim-nomadnet: setup complete. Restart Neovim.", vim.log.levels.INFO)
    end,
  },
}
