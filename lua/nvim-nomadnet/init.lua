-- nvim-nomadnet/init.lua
--
-- Neovim plugin for NomadNet — decentralized mesh messaging, directory,
-- and node browsing over Reticulum / LXMF.
--
-- Requires:
--   - Python 3 with pynvim (`pip install pynvim`)
--   - nomadnet-core (`pip install nomadnet-core` or local source)
--   - Neovim with Python 3 provider (`:checkhealth provider.python`)
--
-- Quick start:
--   1. :NvaStart            Start NomadNet (creates/loads identity)
--   2. :NvaConversations    Open conversation list
--   3. :NvaNetwork          Open network announce browser
--   4. :NvaChannels         Open RRC channel list
--   5. :NvaDirectory        Open peer directory
--   6. :NvaSync             Trigger LXMF sync
--   7. :NvaQuit             Stop NomadNet
--
-- Keybindings (in nomadnet buffers):
--   <CR>     Open / select item under cursor
--   <Tab>    Cycle views (conv → network → channels → directory)
--   r        Refresh current view
--   q        Close current buffer / quit view
--   ?       Toggle help
--

local M = {}

-- ── Configuration ────────────────────────────────────────────────

M.config = {
  --- Path to nomadnet config directory (nil = default ~/.nomadnetwork)
  configdir = nil,
  --- Path to RNS config directory (nil = default ~/.reticulum)
  rnsconfigdir = nil,
  --- Keymap prefix used for nomadnet buffers
  map_prefix = "<LocalLeader>n",
  --- Default window width for detail buffers
  detail_width = 80,
  --- Enable verbose logging from RNS
  verbose = false,
}

-- ── State ────────────────────────────────────────────────────────

local state = {
  running = false,
  buf_conv_list = nil,
  buf_network = nil,
  buf_channels = nil,
  buf_directory = nil,
  current_view = nil,        -- "conversations" | "network" | "channels" | "directory"
}

-- ── Helper: pretty-print helpers ─────────────────────────────────

local function identity_short(hash_hex)
  if not hash_hex then return "???" end
  return string.sub(hash_hex, 1, 8) .. ".." .. string.sub(hash_hex, -8)
end

local function trust_label(level)
  local labels = { [0x00] = "⚠", [0x01] = "✗", [0x02] = "?", [0xFF] = "✓" }
  return labels[level] or "?"
end

local function trust_name(level)
  local names = { [0x00] = "warning", [0x01] = "untrusted", [0x02] = "unknown", [0xFF] = "trusted" }
  return names[level] or "unknown"
end

local function format_timestamp(ts)
  if not ts or ts == 0 then return "---" end
  return os.date("%Y-%m-%d %H:%M", ts)
end

-- ── View helpers ─────────────────────────────────────────────────

local function setup_nomadnet_buffer(buf, name, title)
  vim.api.nvim_buf_set_option(buf, "buftype", "nofile")
  vim.api.nvim_buf_set_option(buf, "bufhidden", "wipe")
  vim.api.nvim_buf_set_option(buf, "filetype", "nomadnet")
  vim.api.nvim_buf_set_option(buf, "modified", false)
  vim.api.nvim_buf_set_option(buf, "swapfile", false)
  vim.api.nvim_buf_set_name(buf, "nomadnet://" .. name)
  if title then
    vim.api.nvim_buf_set_var(buf, "nomadnet_title", title)
  end
end

local function nomadnet_buf_map(buf, lhs, rhs, desc)
  local opts = { noremap = true, silent = true, desc = desc }
  pcall(vim.api.nvim_buf_set_keymap, buf, "n", lhs, rhs, opts)
end

-- ── Helper: check for error response from Python ─────────────────

-- Tracks whether we've already notified the user about startup delay
-- for each view, so refresh doesn't spam notifications.
local _notified_startup = {}

local function check_response(result, view_name)
  if result == nil then return nil end
  if type(result) == "table" and result.error then
    if view_name and not _notified_startup[view_name] then
      vim.notify(result.error, vim.log.levels.WARN)
      _notified_startup[view_name] = true
    end
    return nil
  end
  return result
end

-- ── Helper: show a friendly "not ready yet" buffer ───────────────

local function show_waiting_buffer(view, title, message)
  -- Track which view we're waiting for so `r` can try re-opening it
  state.current_view = view
  -- Reuse existing waiting buffer if it's still valid to avoid E95
  local buf = nil
  for _, b in ipairs(vim.api.nvim_list_bufs()) do
    if vim.api.nvim_buf_is_valid(b) and vim.fn.bufname(b) == "nomadnet://waiting" then
      buf = b
      break
    end
  end
  if not buf then
    buf = vim.api.nvim_create_buf(false, true)
    setup_nomadnet_buffer(buf, "waiting", title or "NomadNet")
  end
  local lines = {
    "  NomadNet",
    string.rep("─", 60),
    "",
    "  " .. (message or "NomadNet is starting up..."),
    "",
    "  ┌─ Help ─────────────────────────────┐",
    "  │ r    Refresh this view             │",
    "  │ q    Close                         │",
    "  │ :NvaStatus  Check startup status   │",
    "  │ :messages  Check for errors        │",
    "  └────────────────────────────────────┘",
    "",
    "  NomadNet will be ready once the Reticulum network",
    "  stack has finished initialising.",
  }
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)
  nomadnet_buf_map(buf, "r", ":lua require'nvim-nomadnet'.refresh()<CR>", "Refresh")
  nomadnet_buf_map(buf, "q", ":bdelete<CR>", "Close")
  vim.api.nvim_set_current_buf(buf)
end

-- ── Render conversations list ────────────────────────────────────

local function render_conversations()
  vim.notify("[debug] render_conversations called", vim.log.levels.DEBUG)
  local ok, convs = pcall(vim.fn["NvaConversations"])
  if not ok or not convs then
    vim.api.nvim_err_writeln("NomadNet not running. Use :NvaStart")
    return
  end
  convs = check_response(convs, "conversations")
  if not convs then
    show_waiting_buffer("conversations", "Conversations",
      "Waiting for NomadNet conversations...")
    return
  end

  local buf = state.buf_conv_list
  if not buf or not vim.api.nvim_buf_is_valid(buf) then
    buf = vim.api.nvim_create_buf(false, true)
    state.buf_conv_list = buf
    setup_nomadnet_buffer(buf, "conversations", "Conversations")
  end

  local lines = {}
  table.insert(lines, "  NomadNet — Conversations")
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if #convs == 0 then
    table.insert(lines, "  (no conversations yet — wait for messages or start one)")
  else
    for _, c in ipairs(convs) do
      local src_hash = c[1]  -- source_hash_hex
      local display  = c[2] or identity_short(src_hash)
      local trust    = c[3]
      local unread   = c[5] or 0
      local last_act = format_timestamp(c[6])

      local prefix = ""
      if unread > 0 then
        prefix = "✉" .. tostring(unread) .. " "
      end
      local icon = trust_label(trust)
      table.insert(lines, string.format("%s%s %s %s  %s",
        prefix, icon, display, string.rep(" ", math.max(1, 32 - #display)),
        last_act))
    end
  end

  -- Store entries safely (Neovim set_var corrupts float keys in tables)
  local safe_convs = {}
  for _, c in ipairs(convs) do
    safe_convs[#safe_convs + 1] = { c[1], c[2], c[3], c[5], c[6] }
  end
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)
  vim.api.nvim_buf_set_var(buf, "nomadnet_entries", safe_convs)

  -- Keymaps
  nomadnet_buf_map(buf, "<CR>",  ":lua require'nvim-nomadnet'.open_conversation()<CR>",  "Open conversation")
  nomadnet_buf_map(buf, "r",    ":lua require'nvim-nomadnet'.refresh()<CR>",             "Refresh")
  nomadnet_buf_map(buf, "q",    ":bdelete<CR>",                                          "Close")
  nomadnet_buf_map(buf, "d",    ":lua require'nvim-nomadnet'.delete_conversation()<CR>", "Delete conversation")
  nomadnet_buf_map(buf, "n",    ":NvaSync<CR>:lua require'nvim-nomadnet'.refresh()<CR>",  "Sync messages")

  vim.api.nvim_set_current_buf(buf)
  state.current_view = "conversations"
end

-- ── Render conversation messages ─────────────────────────────────

local function render_conversation_messages(src_hash_hex, display_name)
  local ok, msgs = pcall(vim.fn["NvaConversationMessages"], src_hash_hex)
  if not ok then return end
  msgs = check_response(msgs)
  if not msgs then return end

  local buf = vim.api.nvim_create_buf(false, true)
  setup_nomadnet_buffer(buf, "msg-" .. identity_short(src_hash_hex), display_name or "Message")

  local lines = {}
  table.insert(lines, "  " .. (display_name or identity_short(src_hash_hex)))
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if msgs and #msgs > 0 then
    -- Messages sorted newest last
    for _, m in ipairs(msgs) do
      local ts = format_timestamp(m.timestamp)
      local title = m.title and #m.title > 0 and m.title or "(no subject)"
      local content = m.content or ""
      local method_labels = { ["DIRECT"] = "→", ["PROPAGATED"] = "⬆", ["OPPORTUNISTIC"] = "↷" }
      local method = method_labels[m.method] or "→"
      table.insert(lines, string.format("  %s %s  %s", method, ts, title))
      table.insert(lines, string.rep("─", 50))
      for _, cl in ipairs(vim.split(content, "\n")) do
        table.insert(lines, "  " .. cl)
      end
      table.insert(lines, "")
    end
  else
    table.insert(lines, "  (no messages)")
  end

  table.insert(lines, "")
  table.insert(lines, string.rep("─", 50))
  table.insert(lines, "  Press 'c' to compose, 'r' to refresh")

  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)

  nomadnet_buf_map(buf, "c",  ":lua require'nvim-nomadnet'.compose_message('" .. src_hash_hex .. "')<CR>", "Compose message")
  nomadnet_buf_map(buf, "r",  (":lua require'nvim-nomadnet'.show_conversation('%s')<CR>"):format(src_hash_hex), "Refresh")
  nomadnet_buf_map(buf, "q",  ":bdelete<CR>", "Close")
  nomadnet_buf_map(buf, "m",  ":lua require'nvim-nomadnet'.mark_read('" .. src_hash_hex .. "')<CR>", "Mark read")

  vim.api.nvim_set_current_buf(buf)
end

-- ── Render network announces ─────────────────────────────────────

local function render_network()
  vim.notify("[debug] render_network called", vim.log.levels.DEBUG)
  local ok, announces = pcall(vim.fn["NvaNetworkAnnounces"])
  if not ok or not announces then
    vim.api.nvim_err_writeln("NomadNet not running.")
    return
  end
  announces = check_response(announces, "network")
  if not announces then
    show_waiting_buffer("network", "Network",
      "Waiting for NomadNet network announces...")
    return
  end

  local buf = state.buf_network
  if not buf or not vim.api.nvim_buf_is_valid(buf) then
    buf = vim.api.nvim_create_buf(false, true)
    state.buf_network = buf
    setup_nomadnet_buffer(buf, "network", "Network")
  end

  local lines = {}
  table.insert(lines, "  NomadNet — Network Announces")
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if #announces == 0 then
    table.insert(lines, "  (no announces yet — wait for network activity)")
  else
    for _, a in ipairs(announces) do
      local ts    = format_timestamp(a[1])
      local sh    = identity_short(a[2])
      local data  = a[3] or ""
      local atype = a[4] or "?"
      local icon  = (atype == "node") and "🖥" or (atype == "pn" and "⬆" or "👤")
      -- Trim and sanitize announce data (remove newlines, truncate)
      local safe_data = (data or ""):gsub("[\r\n]", " "):sub(1, 48)
      table.insert(lines, string.format("  %s %s %s  %s", icon, ts, sh, safe_data))
    end
  end

  -- Store entries without float timestamps (Neovim bug: set_var corrupts float keys)
  local safe_entries = {}
  for _, a in ipairs(announces) do
    table.insert(safe_entries, { a[2], a[3], a[4] })
  end
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)
  vim.api.nvim_buf_set_var(buf, "nomadnet_entries", safe_entries)

  nomadnet_buf_map(buf, "<CR>", ":lua require'nvim-nomadnet'.open_announce()<CR>",             "Open announce")
  nomadnet_buf_map(buf, "a",    ":lua require'nvim-nomadnet'.add_announce_to_directory()<CR>",  "Add to directory")
  nomadnet_buf_map(buf, "r",    ":lua require'nvim-nomadnet'.refresh()<CR>",                    "Refresh")
  nomadnet_buf_map(buf, "q",    ":bdelete<CR>",                                                 "Close")
  nomadnet_buf_map(buf, "u",    ":lua require'nvim-nomadnet'.fetch_url()<CR>",                  "Fetch URL")

  vim.api.nvim_set_current_buf(buf)
  state.current_view = "network"
end

-- ── Render directory ─────────────────────────────────────────────

local function render_directory()
  vim.notify("[debug] render_directory called", vim.log.levels.DEBUG)
  local ok, entries = pcall(vim.fn["NvaDirectory"])
  if not ok or not entries then
    vim.api.nvim_err_writeln("NomadNet not running.")
    return
  end
  entries = check_response(entries, "directory")
  if not entries then
    show_waiting_buffer("directory", "Directory",
      "Waiting for NomadNet peer directory...")
    return
  end

  local buf = state.buf_directory
  if not buf or not vim.api.nvim_buf_is_valid(buf) then
    buf = vim.api.nvim_create_buf(false, true)
    state.buf_directory = buf
    setup_nomadnet_buffer(buf, "directory", "Directory")
  end

  local lines = {}
  table.insert(lines, "  NomadNet — Peer Directory")
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if #entries == 0 then
    table.insert(lines, "  (directory empty)")
  else
    for _, e in ipairs(entries) do
      local sh     = identity_short(e[1])
      local name   = e[2] or sh
      local icon   = trust_label(e[3])
      local node   = e[4] and "🖥" or ""
      table.insert(lines, string.format("  %s %-28s %s %s", icon, name, sh, node))
    end
  end

  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)

  -- Store entries for linkability
  local safe_entries = {}
  for _, e in ipairs(entries) do
    safe_entries[#safe_entries + 1] = { e[1], e[2], e[3], e[4], e[7], e[8] }
  end
  vim.api.nvim_buf_set_var(buf, "nomadnet_entries", safe_entries)

  nomadnet_buf_map(buf, "<CR>", ":lua require'nvim-nomadnet'.open_directory_entry()<CR>", "Browse")
  nomadnet_buf_map(buf, "a",    ":lua require'nvim-nomadnet'.add_to_directory()<CR>",       "Add by hash")
  nomadnet_buf_map(buf, "d",    ":lua require'nvim-nomadnet'.remove_from_directory()<CR>",  "Remove entry")
  nomadnet_buf_map(buf, "r",    ":lua require'nvim-nomadnet'.refresh()<CR>",                "Refresh")
  nomadnet_buf_map(buf, "q",    ":bdelete<CR>",                                             "Close")

  vim.api.nvim_set_current_buf(buf)
  state.current_view = "directory"
end

-- ── Render RRC channels ──────────────────────────────────────────

local function render_channels()
  vim.notify("[debug] render_channels called", vim.log.levels.DEBUG)
  local ok, channels = pcall(vim.fn["NvaRRCChannels"])
  if not ok or not channels then
    vim.api.nvim_err_writeln("NomadNet not running.")
    return
  end
  channels = check_response(channels, "channels")
  if not channels then
    show_waiting_buffer("channels", "Channels",
      "Waiting for NomadNet RRC channels...")
    return
  end

  local buf = state.buf_channels
  if not buf or not vim.api.nvim_buf_is_valid(buf) then
    buf = vim.api.nvim_create_buf(false, true)
    state.buf_channels = buf
    setup_nomadnet_buffer(buf, "channels", "RRC Channels")
  end

  local lines = {}
  table.insert(lines, "  NomadNet — RRC Channels")
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if #channels == 0 then
    table.insert(lines, "  (no channels joined)")
  else
    for _, ch in ipairs(channels) do
      local name = ch.name or identity_short(ch.hash)
      local rooms = #ch.rooms
      table.insert(lines, string.format("  💬 %s  (%d rooms)", name, rooms))
    end
  end

  -- Store entries safely (Neovim set_var corrupts float keys)
  local safe_channels = {}
  for _, ch in ipairs(channels) do
    safe_channels[#safe_channels + 1] = { ch.hash, ch.name, ch.rooms }
  end
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)
  vim.api.nvim_buf_set_var(buf, "nomadnet_entries", safe_channels)

  nomadnet_buf_map(buf, "<CR>", ":lua require'nvim-nomadnet'.open_channel()<CR>", "Open channel")
  nomadnet_buf_map(buf, "r",    ":lua require'nvim-nomadnet'.refresh()<CR>",     "Refresh")
  nomadnet_buf_map(buf, "q",    ":bdelete<CR>",                                   "Close")

  vim.api.nvim_set_current_buf(buf)
  state.current_view = "channels"
end

-- ── Public API functions ─────────────────────────────────────────

function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})
  if M.config.verbose then
    vim.env.NVA_VERBOSE = "1"
  end

  -- Add plugin syntax directory to runtime path (for nomadnet filetype)
  local plugin_dir = vim.fn.stdpath("data") .. "/lazy/nvim-nomadnet"
  if vim.fn.isdirectory(plugin_dir .. "/syntax") == 1 then
    vim.cmd("set runtimepath^=" .. plugin_dir)
  end

  -- Create user commands
  -- NvaStart is registered by the Python plugin (nva.py) as a @pynvim.command.
  -- It runs the NomadNet core startup in the Python host process.
  -- No Lua wrapper needed — the Python command is auto-discovered from rplugin.vim.
  -- The M.start() helper below calls it via vim.cmd.

  vim.api.nvim_create_user_command("NvaConversations", function()
    render_conversations()
  end, {})

  vim.api.nvim_create_user_command("NvaNetwork", function()
    render_network()
  end, {})

  vim.api.nvim_create_user_command("NvaChannels", function()
    render_channels()
  end, {})

  vim.api.nvim_create_user_command("NvaDirectory", function()
    render_directory()
  end, {})

  -- NvaSync and NvaStop are registered by the Python plugin (nva.py).
  vim.api.nvim_create_user_command("NvaRefresh", function()
    M.refresh()
  end, {})

  -- Register leader keymaps + which-key group label
  local nmaps = {
    Nc = { "<cmd>NvaConversations<CR>", "Conversations" },
    Nn = { "<cmd>NvaNetwork<CR>",       "Network" },
    Nh = { "<cmd>NvaChannels<CR>",      "Channels" },
    Nd = { "<cmd>NvaDirectory<CR>",     "Directory" },
    Ns = { "<cmd>NvaSync<CR>",          "Sync" },
  }
  -- Always set actual keymaps so they work regardless of which-key
  for key, spec in pairs(nmaps) do
    vim.keymap.set("n", "<leader>" .. key, spec[1], { desc = spec[2], noremap = true, silent = true })
  end
  -- Register which-key group label (silently if which-key not available)
  local wk_ok, wk = pcall(require, "which-key")
  if wk_ok and wk.add then
    wk.add({ { "<leader>N", group = "NomadNet" } })
    -- Register individual key descriptions in which-key too
    for key, spec in pairs(nmaps) do
      wk.add({ { "<leader>" .. key, spec[1], desc = spec[2] } })
    end
  end

  -- Command to toggle verbose mode for diagnostics
  vim.api.nvim_create_user_command("NvaDebug", function()
    if vim.env.NVA_VERBOSE then
      vim.env.NVA_VERBOSE = nil
      vim.notify("NomadNet verbose mode disabled", vim.log.levels.INFO)
    else
      vim.env.NVA_VERBOSE = "1"
      vim.notify("NomadNet verbose mode enabled (restart required)", vim.log.levels.INFO)
    end
  end, {})

  -- Command to view the log file
  vim.api.nvim_create_user_command("NvaLog", function()
    local logfile = vim.fn.expand("~/.nomadnetwork/nvim-nomadnet.log")
    if vim.fn.filereadable(logfile) == 1 then
      vim.cmd("tabedit " .. logfile)
      vim.bo.filetype = "log"
      vim.bo.modified = false
      vim.api.nvim_buf_set_keymap(0, "n", "q", ":q<CR>", { noremap = true, silent = true, desc = "Close log" })
    else
      vim.notify("Log file not found at " .. logfile, vim.log.levels.WARN)
    end
  end, {})

  -- Command to check startup status
  vim.api.nvim_create_user_command("NvaStatus", function()
    local ok, ident = pcall(vim.fn["NvaIdentity"])
    if ok and ident then
      if ident[1] then
        vim.notify(string.format("NomadNet running. Identity: %s, Name: %s",
          identity_short(ident[1]), ident[2] or "?"), vim.log.levels.INFO)
      elseif ident[3] then
        vim.notify(ident[3], vim.log.levels.WARN)
      end
    else
      vim.notify("NomadNet not started. Use :NvaStart", vim.log.levels.WARN)
    end
  end, {})

  -- Tab mapping: cycle through views
  vim.api.nvim_set_keymap("n", "<Plug>(nomadnet-cycle)",
    ":lua require'nvim-nomadnet'.cycle_view()<CR>",
    { noremap = true, silent = true, desc = "Cycle NomadNet views" })
end

function M.start(configdir, rnsconfigdir)
  local args = ""
  if configdir then args = args .. " " .. vim.fn.shellescape(configdir) end
  if rnsconfigdir then args = args .. " " .. vim.fn.shellescape(rnsconfigdir) end
  pcall(vim.api.nvim_command, "NvaStart" .. args)
  vim.notify("NomadNet starting (initialising Reticulum network)...", vim.log.levels.INFO)
end

function M.on_startup_began()
  state.running = false
  vim.notify("NomadNet is starting up (initialising Reticulum network)...", vim.log.levels.INFO)
end

function M.on_startup_complete()
  state.running = true
  _notified_startup = {}  -- reset so restart shows notifications again
  vim.notify("NomadNet started successfully!", vim.log.levels.INFO)
end

function M.on_stop()
  state.running = false
  _notified_startup = {}  -- reset so next start shows notifications
  vim.notify("NomadNet stopped.", vim.log.levels.INFO)
end

function M.stop()
  pcall(vim.api.nvim_command, "NvaStop")
end

function M.refresh()
  if state.current_view == "conversations" then
    render_conversations()
  elseif state.current_view == "network" then
    render_network()
  elseif state.current_view == "channels" then
    render_channels()
  elseif state.current_view == "directory" then
    render_directory()
  end
end

function M.cycle_view()
  local views = { "conversations", "network", "channels", "directory" }
  local idx = 1
  for i, v in ipairs(views) do
    if v == state.current_view then
      idx = (i % #views) + 1
      break
    end
  end
  if views[idx] == "conversations" then render_conversations()
  elseif views[idx] == "network" then render_network()
  elseif views[idx] == "channels" then render_channels()
  elseif views[idx] == "directory" then render_directory()
  end
end

function M.open_conversation()
  local buf = vim.api.nvim_get_current_buf()
  local entries = vim.api.nvim_buf_get_var(buf, "nomadnet_entries")
  if not entries then return end

  local line = vim.fn.line(".") - 3  -- skip header lines
  if line < 1 or line > #entries then return end

  -- entries[line] = { src_hash, display_name, trust_level, unread, last_activity }
  local entry = entries[line]
  local src_hash = entry[1]
  local display  = entry[2] or identity_short(src_hash)
  render_conversation_messages(src_hash, display)
end

function M.show_conversation(src_hash_hex)
  render_conversation_messages(src_hash_hex, nil)
end

function M.compose_message(src_hash_hex)
  vim.cmd("new")
  local buf = vim.api.nvim_get_current_buf()
  vim.api.nvim_buf_set_option(buf, "buftype", "acwrite")
  vim.api.nvim_buf_set_option(buf, "filetype", "nomadnet-compose")
  vim.api.nvim_buf_set_name(buf, "nomadnet://compose/" .. identity_short(src_hash_hex))

  local lines = {
    ("To: %s"):format(src_hash_hex),
    "Subject: ",
    "",
    "-- Write your message below this line --",
    "",
  }
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(buf, "modified", false)

  nomadnet_buf_map(buf, "<C-s>",
    (":lua require'nvim-nomadnet'.send_composed('%s')<CR>"):format(src_hash_hex),
    "Send message")
  nomadnet_buf_map(buf, "q", ":bdelete!<CR>", "Cancel")

  vim.api.nvim_set_current_buf(buf)
end

function M.send_composed(src_hash_hex)
  local buf = vim.api.nvim_get_current_buf()
  local lines = vim.api.nvim_buf_get_lines(buf, 0, -1)

  -- Parse subject from line 2
  local subject = ""
  local content_lines = {}
  local in_content = false
  for i, l in ipairs(lines) do
    if i == 2 then
      subject = l:match("^Subject: (.+)$") or ""
    end
    if in_content then
      table.insert(content_lines, l)
    end
    if l:match("^%-%-") then
      in_content = true
    end
  end

  local content = table.concat(content_lines, "\n")
  content = content:gsub("^[\n\r]+", "")  -- strip leading newlines

  if #content == 0 then
    vim.notify("Nothing to send!", vim.log.levels.WARN)
    return
  end

  pcall(vim.fn["NvaSendMessage"], src_hash_hex, content, subject)
  vim.notify("Message sent!", vim.log.levels.INFO)
  vim.cmd("bdelete!")
end

function M.mark_read(src_hash_hex)
  pcall(vim.fn["NvaMarkRead"], src_hash_hex)
  vim.notify("Marked as read")
end

function M.delete_conversation()
  local buf = vim.api.nvim_get_current_buf()
  local entries = vim.api.nvim_buf_get_var(buf, "nomadnet_entries")
  if not entries then return end

  local line = vim.fn.line(".") - 3
  if line < 1 or line > #entries then return end

  -- entries[line] = { src_hash, display_name, trust_level, unread, last_activity }
  local src_hash = entries[line][1]
  local confirm = vim.fn.confirm("Delete this conversation?", "&Yes\n&No", 2)
  if confirm == 1 then
    pcall(vim.fn["NvaDeleteConversation"], src_hash)
    render_conversations()
    vim.notify("Conversation deleted")
  end
end

function M.open_directory_entry()
  local buf = vim.api.nvim_get_current_buf()
  local ok, entries = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_entries")
  if not ok or not entries then return end

  local line = vim.fn.line(".") - 3
  if line < 1 or line > #entries then return end

  local entry = entries[line]
  -- entry = { src_hash, display_name, trust_level, hosts_node, sort_rank, notes }
  local src_hash = entry[1]
  local display  = entry[2] or identity_short(src_hash)
  local hosts_node = entry[4]
  local notes = entry[6] or ""

  -- Show an info buffer with actions
  local info = vim.api.nvim_create_buf(false, true)
  setup_nomadnet_buffer(info, "dir-" .. identity_short(src_hash), display)

  local lines = {
    "  " .. display,
    string.rep("─", 50),
    "",
    ("  Hash:  %s"):format(src_hash),
    ("  Trust: %s"):format(trust_name(entry[3])),
  }
  if hosts_node then
    table.insert(lines, "  Hosts: node (🖥)")
  end
  if notes and #notes > 0 then
    table.insert(lines, "")
    table.insert(lines, "  Notes:")
    for _, nl in ipairs(vim.split(notes, "\n")) do
      table.insert(lines, "    " .. nl)
    end
  end
  table.insert(lines, "")
  table.insert(lines, "  ┌─ Actions ────────────────────────────────┐")

  if hosts_node then
    -- Pad to 46 chars total (2 indent + 44 box). Box = │ + ' ' + text + padding + ' │' = 44
    local browse_text = ("<CR>  Browse node  (%s)"):format(identity_short(src_hash))
    local pad = string.rep(" ", 40 - #browse_text)
    table.insert(lines, "  │ " .. browse_text .. pad .. " │")
  end
  table.insert(lines, "  │ m     Send message                       │")
  table.insert(lines, "  └──────────────────────────────────────────┘")

  vim.api.nvim_buf_set_lines(info, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(info, "modified", false)

  if hosts_node then
    nomadnet_buf_map(info, "<CR>",
      (":lua require'nvim-nomadnet'.fetch_page('lxmf@%s/page/index.mu')<CR>"):format(src_hash),
      "Browse node")
  end
  nomadnet_buf_map(info, "m",
    (":lua require'nvim-nomadnet'.compose_message('%s')<CR>"):format(src_hash),
    "Send message")
  nomadnet_buf_map(info, "q", ":bdelete<CR>", "Close")

  vim.api.nvim_set_current_buf(info)
end

function M.open_announce()
  local buf = vim.api.nvim_get_current_buf()
  local entries = vim.api.nvim_buf_get_var(buf, "nomadnet_entries")
  if not entries then return end

  local line = vim.fn.line(".") - 3
  if line < 1 or line > #entries then return end

  local announce = entries[line]
  -- announce = { src_hash, data, atype } (safe entries, no floats)
  local src_hash = announce[1]
  local data     = announce[2]
  local atype    = announce[3]

  -- For nodes, show a mini info buffer
  local info = vim.api.nvim_create_buf(false, true)
  setup_nomadnet_buffer(info, "announce-" .. identity_short(src_hash), "Announce")

  local data_preview = (data or ""):gsub("[\r\n]", " "):sub(1, 60)

  -- Store announce info so add_announce_to_directory works from this buffer
  pcall(vim.api.nvim_buf_set_var, info, "nomadnet_announce_info", { src_hash, data, atype })

  local lines = {
    "  Announce Info",
    string.rep("─", 50),
    "",
    ("  Hash:  %s"):format(src_hash),
    ("  Type:  %s"):format(atype),
  }
  if data_preview and #data_preview > 0 then
    table.insert(lines, ("  Data:  %s"):format(data_preview))
  end
  table.insert(lines, "")
  table.insert(lines, "  ┌─ Actions ────────────────────────────────┐")
  table.insert(lines, ("  │ <CR>  Browse node                        │"))
  table.insert(lines, ("  │ a     Add to directory                   │"))
  table.insert(lines, "  └──────────────────────────────────────────┘")

  vim.api.nvim_buf_set_lines(info, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(info, "modified", false)

  nomadnet_buf_map(info, "<CR>",
    (":lua require'nvim-nomadnet'.fetch_page('lxmf@%s/page/index.mu')<CR>"):format(src_hash),
    "Browse")
  nomadnet_buf_map(info, "a",
    (":lua require'nvim-nomadnet'.add_announce_to_directory()<CR>"),
    "Add to directory")
  nomadnet_buf_map(info, "q", ":bdelete<CR>", "Close")

  vim.api.nvim_set_current_buf(info)
end

function M.open_channel()
  local buf = vim.api.nvim_get_current_buf()
  local entries = vim.api.nvim_buf_get_var(buf, "nomadnet_entries")
  if not entries then return end

  local line = vim.fn.line(".") - 3
  if line < 1 or line > #entries then return end

  -- entries[line] = { hash, name, rooms }
  local ch = entries[line]
  local ch_hash = ch[1]
  local ch_name = ch[2]
  local ok, msgs = pcall(vim.fn["NvaRRCMessages"], ch_hash)
  if not ok then return end

  local m_buf = vim.api.nvim_create_buf(false, true)
  setup_nomadnet_buffer(m_buf, "rrc-" .. identity_short(ch_hash), ch_name or "Channel")

  local lines = {}
  table.insert(lines, "  " .. (ch.name or "RRC Channel"))
  table.insert(lines, string.rep("─", 60))
  table.insert(lines, "")

  if msgs and #msgs > 0 then
    for _, m in ipairs(msgs) do
      local ts = format_timestamp(m.timestamp)
      local sender = m.notice and "" or (m.sender or "???")
      local prefix = m.notice and "!" or ">"
      table.insert(lines, string.format("  %s %s %s", ts, sender, m.content or ""))
    end
  else
    table.insert(lines, "  (no messages)")
  end

  vim.api.nvim_buf_set_lines(m_buf, 0, -1, false, lines)
  vim.api.nvim_buf_set_option(m_buf, "modified", false)
  nomadnet_buf_map(m_buf, "q", ":bdelete<CR>", "Close")

  vim.api.nvim_set_current_buf(m_buf)
end

-- ── Directory Management ─────────────────────────────────────────

function M.add_to_directory()
  -- Prompt for a source hash and optional display name, then add to directory
  vim.ui.input({ prompt = "Source hash (hex): " }, function(hash)
    if not hash or #hash == 0 then return end
    vim.ui.input({ prompt = "Display name (optional): " }, function(name)
      local result = pcall(vim.fn["NvaAddToDirectory"], hash, name or "")
      if result then
        vim.notify("Added to directory", vim.log.levels.INFO)
        M.refresh()
      else
        vim.notify("Failed to add to directory", vim.log.levels.ERROR)
      end
    end)
  end)
end

function M.add_announce_to_directory()
  -- Add the announce under the cursor to the directory
  local buf = vim.api.nvim_get_current_buf()
  local ok, entries = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_entries")

  local src_hash, data, atype
  if ok and entries then
    -- Network announce list buffer: get entry by line number
    local line = vim.fn.line(".") - 3
    if line < 1 or line > #entries then return end
    local announce = entries[line]
    src_hash = announce[1]
    data     = announce[2] or ""
    atype    = announce[3] or "?"
  else
    -- Announce detail buffer: read buffer variable set in open_announce()
    local ok2, info = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_announce_info")
    if not ok2 or not info then return end
    src_hash = info[1]
    data     = info[2] or ""
    atype    = info[3] or "?"
  end

  -- Use announce data as the display name if it looks like a name
  local display_name = nil
  if data and #data > 0 and not data:match("^[a-fA-F0-9]+$") then
    display_name = data
  end

  local result = vim.fn["NvaAddToDirectory"](src_hash, display_name or "")
  if type(result) == "table" and result.ok then
    vim.notify("Added " .. atype .. " to directory", vim.log.levels.INFO)
    M.refresh()
  elseif type(result) == "table" and result.info then
    vim.notify(result.info, vim.log.levels.INFO)
  else
    vim.notify("Failed to add to directory", vim.log.levels.ERROR)
  end
end

function M.remove_from_directory()
  local buf = vim.api.nvim_get_current_buf()
  local ok, entries = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_entries")
  if not ok or not entries then return end

  local line = vim.fn.line(".") - 3
  if line < 1 or line > #entries then return end

  local entry = entries[line]
  -- entry = { src_hash, display_name, trust_level, hosts_node, sort_rank, notes }
  local src_hash = entry[1]
  local display  = entry[2] or identity_short(src_hash)

  local confirm = vim.fn.confirm(
    ('Remove "%s" from directory?'):format(display),
    "&Yes\n&No", 2)
  if confirm == 1 then
    local result = vim.fn["NvaRemoveFromDirectory"](src_hash)
    if type(result) == "table" and result.ok then
      vim.notify("Removed from directory", vim.log.levels.INFO)
      M.refresh()
    else
      vim.notify("Failed to remove from directory", vim.log.levels.ERROR)
    end
  end
end

function M.fetch_page(url)
  vim.notify("[debug] fetch_page called: " .. tostring(url), vim.log.levels.DEBUG)
  vim.notify("Fetching " .. url .. " ...")
  vim.notify("[debug] calling NvaFetchPage...", vim.log.levels.DEBUG)
  pcall(vim.fn["NvaFetchPage"], url)
  vim.notify("[debug] NvaFetchPage returned", vim.log.levels.DEBUG)
end

function M.fetch_url()
  vim.ui.input({ prompt = "NomadNet URL: " }, function(input)
    if input and #input > 0 then
      M.fetch_page(input)
    end
  end)
end

-- ── Page link navigation ─────────────────────────────────────────

function M.open_page_link()
  local buf = vim.api.nvim_get_current_buf()
  local ok, links = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_links")
  if not ok or not links or #links == 0 then
    vim.notify("No links on this page", vim.log.levels.INFO)
    return
  end

  local cursor = vim.api.nvim_win_get_cursor(0)
  local row = cursor[1] - 1  -- 0-based
  local col = cursor[2]

  for _, link in ipairs(links) do
    local lrow = link[1]  -- 0-based row
    local lcs = link[2]
    local lce = link[3]
    local url = link[4]
    if lrow == row and col >= lcs and col < lce then
      M.fetch_page(url)
      return
    end
  end

  vim.notify("No link at cursor", vim.log.levels.INFO)
end

function M.next_page_link()
  local buf = vim.api.nvim_get_current_buf()
  local ok, links = pcall(vim.api.nvim_buf_get_var, buf, "nomadnet_links")
  if not ok or not links or #links == 0 then return end

  local cursor = vim.api.nvim_win_get_cursor(0)
  local row = cursor[1] - 1  -- 0-based
  local col = cursor[2]

  -- Find the next link (after current cursor position), wrapping around
  local target
  for i, link in ipairs(links) do
    local lrow = link[1]
    local lcs = link[2]
    if lrow > row or (lrow == row and lcs > col) then
      target = link
      break
    end
  end
  if not target then
    -- Wrap to first link
    target = links[1]
  end

  -- Move cursor to link position
  vim.api.nvim_win_set_cursor(0, { target[1] + 1, target[2] })
end

-- ── Statusline / info ────────────────────────────────────────────

function M.statusline()
  local ok, ident = pcall(vim.fn["NvaIdentity"])
  if ok and ident then
    if ident[1] then
      return "NomadNet: " .. identity_short(ident[1])
    end
    if ident[3] then
      -- ident[3] contains status string (e.g. "NomadNet is still starting up...")
      return "NomadNet: ⏳ init..."
    end
  end
  return "NomadNet: ⏹"
end

-- ── Export ───────────────────────────────────────────────────────

return M
