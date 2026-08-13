"""
Neovim NomadNet Backend (nva.py)

Python plugin that wraps the nomadnet_core library for Neovim.
Implements the UIBackend interface and exposes API methods to Lua.

Usage in Neovim:
    :NvaStart           Start the NomadNet daemon (loads identity, announces)
    :NvaConversations   Open conversation list
    :NvaNetwork         Open network announce browser
    :NvaChannels        Open RRC channel browser
    :NvaDirectory       Open peer directory
    :NvaSync            Trigger LXMF sync
    :NvaQuit            Shutdown NomadNet
"""

import os
import sys
import time
import shlex
import threading
import traceback

import pynvim

# Ensure nomadnet_core is on the path
_srcdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_parentdir = os.path.dirname(_srcdir)
for d in (_parentdir, _srcdir):
    if d not in sys.path:
        sys.path.insert(0, d)


@pynvim.plugin
class NomadNetAgent(object):
    """Neovim RPC plugin wrapping nomadnet_core.

    Design:
        - A single NomadNetworkApp instance is created on :NvaStart.
        - A UIBackend subclass handles lifecycle callbacks.
        - Neovim buffers display data rendered from core state.
        - Lua-side mappings call nvim_exec_lua or vim.fn.rpcrequest to
          bridge back to the appropriate Python method.
    """

    # ──────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────

    def __init__(self, nvim):
        self.nvim = nvim
        self.app = None
        self._rrc_timer = None

    @pynvim.command("NvaStart", nargs="*", sync=False)
    def cmd_start(self, args):
        """Start the NomadNet core. Optionally pass configdir and rnsconfigdir."""
        configdir = args[0] if len(args) > 0 else None
        rnsconfigdir = args[1] if len(args) > 1 else None
        self._start_nomadnet(configdir, rnsconfigdir)

    @pynvim.command("NvaStop", sync=False)
    def cmd_stop(self):
        """Shut down NomadNet core."""
        self._stop_nomadnet()

    @pynvim.command("NvaQuit", sync=False)
    def cmd_quit(self):
        """Shut down and quit."""
        self._stop_nomadnet()

    # ──────────────────────────────────────────────────────────────
    # NomadNet Core Management
    # ──────────────────────────────────────────────────────────────

    def _start_nomadnet(self, configdir=None, rnsconfigdir=None):
        if self.app is not None:
            self.nvim.out_write("NomadNet is already running.\n")
            return

        # Suppress RNS logging for Neovim use unless user opts in
        import RNS
        RNS.loglevel = getattr(RNS, "LOG_DEBUG", 0) if os.environ.get("NVA_VERBOSE") else 0
        RNS.logdest = RNS.LOG_STDOUT

        try:
            from nomadnet_core.core.NomadNetworkApp import NomadNetworkApp

            # Create a custom UIBackend that notifies Neovim
            backend = _NeovimUIBackend(self)

            self.app = NomadNetworkApp(
                configdir=configdir,
                rnsconfigdir=rnsconfigdir,
                daemon=True,
                ui_backend=backend,
            )
            self.nvim.out_write(
                f"NomadNet started. Identity: {self.app.identity}\n"
                f"Display name: {self.app.get_display_name()}\n"
            )

        except Exception as e:
            self.nvim.err_write(f"Failed to start NomadNet: {e}\n")
            traceback.print_exc()

    def _stop_nomadnet(self):
        if self.app is None:
            return
        try:
            self.app.quit()
        except Exception:
            pass
        self.app = None
        self.nvim.out_write("NomadNet stopped.\n")

    # ──────────────────────────────────────────────────────────────
    # Conversation API
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaConversations", sync=True)
    def get_conversations(self, args):
        """Return a list of all conversations.

        Each entry: [source_hash_hex, display_name, trust_level,
                      sort_name, unread_count, last_activity_timestamp, failed_count]
        """
        if self.app is None:
            return []
        from nomadnet_core.core.Conversation import Conversation
        return Conversation.conversation_list(self.app)

    @pynvim.function("NvaConversationMessages", sync=True)
    def get_conversation_messages(self, args):
        """Return messages for a conversation identified by source_hash_hex."""
        if self.app is None:
            return []
        if not args:
            return []

        source_hash_hex = args[0]
        from nomadnet_core.core.Conversation import Conversation
        conv = Conversation(source_hash_hex, self.app)
        result = []
        for msg in conv.messages:
            result.append({
                "hash": msg.get_hash().hex() if msg.get_hash() else "",
                "title": msg.get_title(),
                "content": msg.get_content(),
                "timestamp": msg.get_timestamp(),
                "state": msg.get_state(),
                "method": msg._cached_method if hasattr(msg, '_cached_method') else None,
            })
        # Use source direction so originator's messages are "sent"
        return result

    @pynvim.function("NvaSendMessage", sync=False)
    def send_message(self, args):
        """Send a message to a conversation.

        Args:
            args[0]: source_hash_hex (str)
            args[1]: content (str)
            args[2]: title (str, optional)
        """
        if self.app is None:
            return
        if len(args) < 2:
            return
        source_hash_hex = args[0]
        content = args[1]
        title = args[2] if len(args) > 2 else ""

        from nomadnet_core.core.Conversation import Conversation
        conv = Conversation(source_hash_hex, self.app, initiator=True)
        conv.send(content=content, title=title)

    @pynvim.function("NvaMarkRead", sync=False)
    def mark_read(self, args):
        """Mark a conversation as read."""
        if self.app is None or not args:
            return
        self.app.mark_conversation_read(args[0])

    @pynvim.function("NvaDeleteConversation", sync=False)
    def delete_conversation(self, args):
        """Delete a conversation by source_hash_hex."""
        if self.app is None or not args:
            return
        from nomadnet_core.core.Conversation import Conversation
        Conversation.delete_conversation(args[0], self.app)

    # ──────────────────────────────────────────────────────────────
    # Network / Announce Stream
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaNetworkAnnounces", sync=True)
    def get_network_announces(self, args):
        """Return the announce stream.

        Each entry: (timestamp, source_hash_hex, app_data_text, type_str)
        where type_str is "node", "peer", or "pn".
        """
        if self.app is None:
            return []
        stream = self.app.directory.announce_stream
        result = []
        for entry in stream:
            ts, sh, ad, at = entry
            app_data_text = ad.decode("utf-8", errors="replace") if isinstance(ad, bytes) else str(ad)
            result.append((ts, sh.hex() if isinstance(sh, bytes) else sh, app_data_text, at))
        return result

    @pynvim.function("NvaNodePages", sync=True)
    def get_node_pages(self, args):
        """Return list of pages served by a node (requires node to be running)."""
        if self.app is None or self.app.node is None:
            return []
        return self.app.node.servedpages

    # ──────────────────────────────────────────────────────────────
    # Page Fetching (Browser Protocol)
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaFetchPage", sync=False)
    def fetch_page(self, args):
        """Fetch a page from a NomadNet node asynchronously.

        args[0]: URL in lxmf@<hash>/path or hash/path format.
        Schedules _on_page_callback when done.
        """
        if self.app is None or not args:
            return
        url = args[0]
        from nomadnet_core.protocol import PageFetcher
        fetcher = PageFetcher(self.app)

        def on_ready(content, meta):
            self._notify_page_result(url, content, meta, None)

        def on_error(code, msg):
            self._notify_page_result(url, None, None, (code, msg))

        fetcher.on_page_ready(on_ready)
        fetcher.on_page_error(on_error)
        fetcher.retrieve_url(url)

    def _notify_page_result(self, url, content, meta, error):
        """Send page fetch result to Neovim buffer."""
        if error:
            self.nvim.async_call(self.nvim.out_write,
                                 f"Page error for {url}: {error[1]}\n")
            return
        self.nvim.async_call(self._display_page, url, content, meta)

    def _display_page(self, url, content, meta):
        buf = self.nvim.current.buffer
        buf[:] = content.split("\n") if content else ["(empty page)"]
        buf.name = f"nomadnet://{url}"
        buf.options["modified"] = False
        buf.options["filetype"] = "nomadnet"
        self.nvim.command("setlocal buftype=nofile nomodifiable")

    # ──────────────────────────────────────────────────────────────
    # Directory
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaDirectory", sync=True)
    def get_directory(self, args):
        """Return all directory entries.

        Each entry: [source_hash_hex, display_name, trust_level, hosts_node,
                     preferred_delivery, identify_on_connect, sort_rank, notes]
        """
        if self.app is None:
            return []
        result = []
        for sh, entry in self.app.directory.directory_entries.items():
            result.append((
                sh.hex() if isinstance(sh, bytes) else sh,
                entry.display_name,
                entry.trust_level,
                entry.hosts_node,
                entry.preferred_delivery,
                entry.identify,
                entry.sort_rank,
                entry.notes,
            ))
        return result

    # ──────────────────────────────────────────────────────────────
    # RRC Channels
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaRRCChannels", sync=True)
    def get_rrc_channels(self, args):
        """Return RRC hub list.

        Each entry: {hash, name, dest_name, rooms, auto_reconnect}
        """
        if self.app is None or self.app.rrc is None:
            return []
        result = []
        for hub in self.app.rrc.hubs:
            result.append({
                "hash": hub.hub_hash.hex() if isinstance(hub.hub_hash, bytes) else hub.hub_hash,
                "name": hub.name,
                "dest_name": hub.dest_name,
                "rooms": list(hub.rooms),
                "auto_reconnect": hub.auto_reconnect,
            })
        return result

    @pynvim.function("NvaRRCMessages", sync=True)
    def get_rrc_messages(self, args):
        """Return messages for a given hub hash (hex)."""
        if self.app is None or self.app.rrc is None or not args:
            return []
        hub_hash_hex = args[0]
        target_hash = bytes.fromhex(hub_hash_hex) if len(hub_hash_hex) > 16 else hub_hash_hex
        for hub in self.app.rrc.hubs:
            h = hub.hub_hash.hex() if isinstance(hub.hub_hash, bytes) else hub.hub_hash
            if h == hub_hash_hex:
                msgs = []
                for room_name, room_msgs in hub.messages.items():
                    for m in room_msgs:
                        msgs.append({
                            "room": room_name,
                            "sender": m.sender,
                            "content": m.content,
                            "timestamp": m.timestamp,
                            "notice": getattr(m, "notice", False),
                        })
                return msgs
        return []

    # ──────────────────────────────────────────────────────────────
    # LXMF Sync
    # ──────────────────────────────────────────────────────────────

    @pynvim.command("NvaSync", sync=False)
    def cmd_sync(self):
        """Request LXMF sync from propagation node."""
        if self.app is None:
            self.nvim.err_write("NomadNet not started. Use :NvaStart first.\n")
            return
        self.app.request_lxmf_sync()
        self.nvim.out_write("LXMF sync requested.\n")

    @pynvim.function("NvaSyncStatus", sync=True)
    def get_sync_status(self, args):
        """Return the current sync status string and progress."""
        if self.app is None:
            return ("Not running", 0)
        status = self.app.get_sync_status()
        progress = self.app.get_sync_progress()
        return (status, progress)

    # ──────────────────────────────────────────────────────────────
    # Identity / Info
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaIdentity", sync=True)
    def get_identity(self, args):
        """Return identity info: [hash_hex, display_name]."""
        if self.app is None:
            return [None, None]
        import RNS
        return [
            RNS.hexrep(self.app.identity.hash, delimit=False),
            self.app.get_display_name(),
        ]

    @pynvim.function("NvaSetDisplayName", sync=False)
    def set_display_name(self, args):
        """Set the display name."""
        if self.app is not None and args:
            self.app.set_display_name(args[0])


# ──────────────────────────────────────────────────────────────────
# UIBackend for Neovim
# ──────────────────────────────────────────────────────────────────

class _NeovimUIBackend:
    """UIBackend implementation that interacts with Neovim.

    Methods are called from the NomadNetworkApp lifecycle hooks.
    We use nvim.async_call to push work onto the main loop.
    """

    def __init__(self, agent):
        self.agent = agent
        self.nvim = agent.nvim

    def on_exit(self, app):
        """Called during NomadNetworkApp shutdown."""
        self.nvim.async_call(self.nvim.out_write, "NomadNet core shut down.\n")

    def on_message_received(self, app):
        """Called when a new LXMF message arrives."""
        self.nvim.async_call(self._notify_message)

    def _notify_message(self):
        try:
            from nomadnet_core.core.Conversation import Conversation
            unread = len(Conversation.unread_conversations)
            if unread > 0:
                self.nvim.out_write(f"\n[+{unread}] New NomadNet message(s)\n")
        except Exception:
            pass

    def get_glyph(self, name):
        """Return an emoji/unicode glyph for status displays."""
        glyphs = {
            "sent": "↑",
            "received": "↓",
            "encrypted": "🔒",
            "unread": "✉",
            "node": "🖥",
            "peer": "👤",
            "check": "✓",
            "cross": "✗",
            "warning": "⚠",
            "unknown": "?",
        }
        return glyphs.get(name)

    def schedule_redraw(self, app, delay=0.0):
        """Request UI refresh after optional delay."""
        # In Neovim we don't need explicit redraw scheduling
        # since commands fetch state synchronously.
        pass
