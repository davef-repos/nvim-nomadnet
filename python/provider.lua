-- Configure Neovim's Python provider to use the nvim-nomadnet venv
-- which has RNS, LXMF, pynvim, and nomadnet-core installed.
local plugin_venv = vim.fn.expand("~/src/NomadNet/nvim-nomadnet/.venv/bin/python3")
if vim.fn.executable(plugin_venv) == 1 then
  vim.g.python3_host_prog = plugin_venv
end
