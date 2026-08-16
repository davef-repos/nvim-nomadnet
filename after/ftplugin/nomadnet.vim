" NomadNet filetype plugin — sets up highlight groups for extmark-based
" micron markup rendering (bold, italic, colors, etc.)

" ── Style highlight groups ───────────────────────────────────────

" Basic text styles
highlight default NomadNetBold       cterm=bold      gui=bold
highlight default NomadNetItalic     cterm=italic    gui=italic
highlight default NomadNetUnderline  cterm=underline gui=underline
highlight default NomadNetKeyword    ctermfg=4       guifg=#569cd6
highlight default NomadNetComment    ctermfg=8       guifg=#6a9955
highlight default NomadNetDivider    ctermfg=8       guifg=#6a9955
highlight default NomadNetHeading    ctermfg=3       guifg=#dcdcaa
highlight default NomadNetLink       cterm=underline ctermfg=6  gui=underline guifg=#4ec9b0
highlight default NomadNetField      cterm=reverse   gui=reverse

" ── Color groups (for `F and `B tags) ────────────────────────────
" ANSI terminal colors — these match the 16 standard ANSI colors
" and are used by the extmark renderer for `F` tags.

highlight default NomadNetFG000   ctermfg=0   guifg=#000000
highlight default NomadNetFG001   ctermfg=1   guifg=#800000
highlight default NomadNetFG002   ctermfg=2   guifg=#008000
highlight default NomadNetFG003   ctermfg=3   guifg=#808000
highlight default NomadNetFG004   ctermfg=4   guifg=#000080
highlight default NomadNetFG005   ctermfg=5   guifg=#800080
highlight default NomadNetFG006   ctermfg=6   guifg=#008080
highlight default NomadNetFG007   ctermfg=7   guifg=#c0c0c0
highlight default NomadNetFG008   ctermfg=8   guifg=#808080
highlight default NomadNetFG009   ctermfg=9   guifg=#ff0000
highlight default NomadNetFG010   ctermfg=10  guifg=#00ff00
highlight default NomadNetFG011   ctermfg=11  guifg=#ffff00
highlight default NomadNetFG012   ctermfg=12  guifg=#0000ff
highlight default NomadNetFG013   ctermfg=13  guifg=#ff00ff
highlight default NomadNetFG014   ctermfg=14  guifg=#00ffff
highlight default NomadNetFG015   ctermfg=15  guifg=#ffffff

highlight default NomadNetBG000   ctermbg=0   guibg=#000000
highlight default NomadNetBG001   ctermbg=1   guibg=#800000
highlight default NomadNetBG002   ctermbg=2   guibg=#008000
highlight default NomadNetBG003   ctermbg=3   guibg=#808000
highlight default NomadNetBG004   ctermbg=4   guibg=#000080
highlight default NomadNetBG005   ctermbg=5   guibg=#800080
highlight default NomadNetBG006   ctermbg=6   guibg=#008080
highlight default NomadNetBG007   ctermbg=7   guibg=#c0c0c0
highlight default NomadNetBG008   ctermbg=8   guibg=#808080
highlight default NomadNetBG009   ctermbg=9   guibg=#ff0000
highlight default NomadNetBG010   ctermbg=10  guibg=#00ff00
highlight default NomadNetBG011   ctermbg=11  guibg=#ffff00
highlight default NomadNetBG012   ctermbg=12  guibg=#0000ff
highlight default NomadNetBG013   ctermbg=13  guibg=#ff00ff
highlight default NomadNetBG014   ctermbg=14  guibg=#00ffff
highlight default NomadNetBG015   ctermbg=15  guibg=#ffffff

" ── Custom color groups (dynamic, created by extmark renderer) ───
" These are generated at render time from the `FT / `BT 6-hex tags.
" We define a few common ones statically as examples:

highlight default NomadNetCustomFGff8800  ctermfg=3   guifg=#ff8800
highlight default NomadNetCustomFGff0000  ctermfg=9   guifg=#ff0000
highlight default NomadNetCustomFG00ff00  ctermfg=10  guifg=#00ff00
highlight default NomadNetCustomFG0000ff  ctermfg=12  guifg=#0000ff

" ── Combined groups ──────────────────────────────────────────────

highlight default NomadNetBoldLink  cterm=bold,underline ctermfg=6  gui=bold,underline guifg=#4ec9b0
highlight default NomadNetItalicLink  cterm=italic,underline ctermfg=6  gui=italic,underline guifg=#4ec9b0
