-- nvim-nomadnet plugin spec for lazy.nvim / LazyVim
--
-- lazy.nvim will clone this repo from GitHub automatically.
-- Update the `url` below when the repo is on GitHub.
--
-- NOTE: Before lazy.nvim bootstrap, your init.lua must set the
-- Python host provider. See README.md for details.

return {
  {
    name = "nvim-nomadnet",
    url = "davef-repos/nvim-nomadnet",  -- update this when on GitHub
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
