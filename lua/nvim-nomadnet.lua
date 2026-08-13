-- nvim-nomadnet/lua/nvim-nomadnet/init.lua → single-file plugin entry
-- Re-exports everything from the main module.
-- Install: place this directory under ~/.local/share/nvim/site/pack/plugins/start/nvim-nomadnet/
-- or use your favourite plugin manager.

local ok, mod = pcall(require, "nvim-nomadnet.init")
if not ok then
  -- fallback: try loading directly
  mod = require("nvim-nomadnet")
end

return mod
