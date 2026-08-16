" Vim syntax file for NomadNet micron-markup pages
" Language:     NomadNet micron markup
" Maintainer:   nvim-nomadnet
" Filenames:    nomadnet://*

if exists("b:current_syntax")
  finish
endif

" Links — [label`url] or [label`url`fields]
" Match links on lines that are not comments
syntax match nomadnetLink  '\[[^]]*\]'  contains=nomadnetLinkURL
syntax match nomadnetLinkURL  '`[^]`]*'  contained

" Headers — >Heading, >>Subheading
syntax match nomadnetH1  '^>[^>].*$'
syntax match nomadnetH2  '^>>[^>].*$'
syntax match nomadnetH3  '^>>>[^>].*$'

" Dividers — ---
syntax match nomadnetDivider  '^-\{1,3}$'

" Highlight groups
highlight default link nomadnetLink       Underlined
highlight default link nomadnetLinkURL    Identifier
highlight default link nomadnetH1         Title
highlight default link nomadnetH2         Title
highlight default link nomadnetH3         Title
highlight default link nomadnetDivider    Comment

let b:current_syntax = "nomadnet"
