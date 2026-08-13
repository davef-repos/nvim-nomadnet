" nvim-nomadnet/plugin/nvim-nomadnet.vim
" Plugin loader for nvim-nomadnet
" Ensures the Python rplugin is registered if pynvim is available.

if exists('g:loaded_nvim_nomadnet')
  finish
endif
let g:loaded_nvim_nomadnet = 1

" Ensure the Python plugin file is in rplugin path for :UpdateRemotePlugins
" The actual registration happens via @pynvim.plugin decorators in nva.py.
" When pynvim is properly installed, running :UpdateRemotePlugins will
" discover the NomadNetAgent class automatically.
