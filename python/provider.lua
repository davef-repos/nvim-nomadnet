-- Configure Neovim's Python provider to use the nvim-nomadnet venv
-- which has RNS, LXMF, pynvim, and nomadnet-core installed.
--
-- This locates the venv relative to the plugin's installed location.
-- When using lazy.nvim, the plugin root is stdpath("data") .. "/lazy/nvim-nomadnet".
-- For other install methods, adjust as needed.

local plugin_root = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
local plugin_venv = plugin_root .. "/.venv/bin/python3"
if vim.fn.executable(plugin_venv) == 1 then
  vim.g.python3_host_prog = plugin_venv
end
