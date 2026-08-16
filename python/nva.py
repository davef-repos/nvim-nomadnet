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
import logging
import faulthandler

import pynvim

# Ensure nomadnet_core and this plugin's python/ dir are on the path
_srcdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_parentdir = os.path.dirname(_srcdir)
for d in (_parentdir, _srcdir):
    if d not in sys.path:
        sys.path.insert(0, d)

# -------------------------------------------------------------------
# Logger — writes to ~/.nomadnetwork/nvim-nomadnet.log
# Handlers are created lazily so logging works even before setup.
# -------------------------------------------------------------------

_log_file = os.path.join(os.path.expanduser("~/.nomadnetwork"), "nvim-nomadnet.log")
_log = logging.getLogger("nvim-nomadnet")

# Enable faulthandler to dump Python thread states on SIGUSR1
# (kill -SIGUSR1 <pid> while frozen)
try:
    faulthandler.enable()
except Exception:
    pass

# Also install a signal handler that dumps all threads to the log
# (fallback in case faulthandler's dump_traceback doesn't reach our file)
import signal as _signal
try:
    _signal.signal(_signal.SIGUSR2, lambda sig, frame: _dump_all_threads())
except Exception:
    pass


def _dump_all_threads():
    """Write all thread stacks to a separate dump file (not the main log)."""
    try:
        import io, traceback
        buf = io.StringIO()
        buf.write(f"All-thread dump at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        buf.write("=" * 60 + "\n")
        for th in threading.enumerate():
            buf.write(f"\n--- Thread: {th.name} (daemon={th.daemon}) ---\n")
            try:
                traceback.print_stack(sys._current_frames().get(th.ident, None), file=buf)
            except Exception:
                buf.write("  (no stack available)\n")
        msg = buf.getvalue()
        dump_file = _log_file.replace(".log", ".dumps")
        with open(dump_file, "a") as f:
            f.write(msg + "\n")
        # Also add a pointer to the dump file in the main log
        _log.info("Thread dump written to %s", dump_file)
    except Exception:
        pass
_log.setLevel(logging.DEBUG)
_log_handler = None


def _init_log():
    global _log_handler
    if _log_handler is not None:
        return
    try:
        _rotate_log()
        # Trim dump file to last 5 dumps
        _trim_dump_file()
        os.makedirs(os.path.dirname(_log_file), exist_ok=True)
        fh = logging.FileHandler(_log_file, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-5s [%(threadName)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        _log.addHandler(fh)
        _log_handler = fh
    except Exception:
        pass


def _trim_dump_file():
    """Keep only the last 5 thread dumps in the dump file."""
    try:
        dump_file = _log_file.replace(".log", ".dumps")
        if not os.path.exists(dump_file):
            return
        with open(dump_file, "r") as f:
            content = f.read()
        # Split on "=== End dump ===" and keep last 5 blocks
        blocks = content.split("=== End dump ===\n")
        if len(blocks) > 5:
            blocks = blocks[-5:]
        with open(dump_file, "w") as f:
            f.write("=== End dump ===\n".join(blocks))
    except Exception:
        pass  # best-effort logging


def _log_debug(msg, *a):
    _init_log()
    _log.debug(msg, *a)


def _log_info(msg, *a):
    _init_log()
    _log.info(msg, *a)


def _log_warn(msg, *a):
    _init_log()
    _log.warning(msg, *a)


def _log_error(msg, *a):
    _init_log()
    _log.error(msg, *a)


def _rotate_log():
    """Trim the log file if it exceeds 500KB."""
    try:
        size = os.path.getsize(_log_file)
        if size > 500 * 1024:
            import io
            kept = []
            with open(_log_file, "r") as f:
                # Keep the last 2000 lines
                all_lines = f.readlines()
            kept = all_lines[-2000:]
            # Keep the first line (oldest for context) + recent lines
            lines_to_write = all_lines[:1] + [f"--- log truncated at {time.ctime()}, was {size} bytes, keeping {len(kept)} lines ---\n"] + kept
            with open(_log_file, "w") as f:
                f.writelines(lines_to_write)
    except Exception:
        pass


# ── Diagnostic helpers ────────────────────────────────────────────

_rpc_watchdog_timer = None
_rpc_watchdog_lock = threading.Lock()


def _start_rpc_watchdog(name):
    """Start a 2-second timer that logs if a sync=True RPC hangs."""
    global _rpc_watchdog_timer
    with _rpc_watchdog_lock:
        if _rpc_watchdog_timer is not None:
            _rpc_watchdog_timer.cancel()

        def _warn():
            _log_error("=== SYNC RPC WATCHDOG: '%s' has been running for >2s ===", name)
            _log_error("Possible deadlock or RNS lock contention. Dumping thread stacks...")
            try:
                with open(_log_file, "a") as f:
                    f.write(f"\n--- Faulthandler dump for frozen RPC '{name}' ---\n")
                    faulthandler.dump_traceback(file=f)
                    f.write("--- End dump ---\n\n")
            except Exception:
                pass

        _rpc_watchdog_timer = threading.Timer(2.0, _warn)
        _rpc_watchdog_timer.daemon = True
        _rpc_watchdog_timer.start()


def _log_rpc_start(name):
    """Log entry into a sync=True RPC."""
    _log_debug(">>> sync RPC '%s' called", name)
    _start_rpc_watchdog(name)


def _log_rpc_end(name, result=None):
    """Log exit from a sync=True RPC."""
    _stop_rpc_watchdog()
    if isinstance(result, dict) and "error" in result:
        _log_debug("<<< sync RPC '%s' -> error: %s", name, result["error"])
    else:
        _log_debug("<<< sync RPC '%s' done (result len=%s)", name,
                     len(result) if isinstance(result, (list, dict)) else "N/A")


def _stop_rpc_watchdog():
    """Cancel the watchdog timer (call when the RPC completes)."""
    global _rpc_watchdog_timer
    with _rpc_watchdog_lock:
        if _rpc_watchdog_timer is not None:
            _rpc_watchdog_timer.cancel()
            _rpc_watchdog_timer = None


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
        self._starting = False       # True while startup is in progress
        self._startup_error = None   # Error string if startup failed

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
        _log_info("NvaStart requested, configdir=%s, rnsconfigdir=%s",
                     configdir, rnsconfigdir)

        if self.app is not None:
            self.nvim.out_write("NomadNet is already running.\n")
            _log_debug("Startup skipped: already running")
            return

        if self._starting:
            self.nvim.out_write("NomadNet is already starting up...\n")
            _log_debug("Startup skipped: already starting")
            return

        self._starting = True
        self._startup_error = None

        # Show immediate feedback — this runs before Reticulum init blocks
        self.nvim.out_write("NomadNet starting up (initialising Reticulum network)...\n")
        self.nvim.command("lua require'nvim-nomadnet'.on_startup_began()")

        # Run startup in a *separate* thread so the pynvim event-loop thread
        # is freed immediately. This is critical because sync=True RPC calls
        # (e.g. NvaNetworkAnnounces, NvaConversations) need the event loop —
        # if RNS.Reticulum() is blocking on it, Neovim hangs.
        #
        # Note: RNS.Reticulum.__init__ calls signal.signal() at the end,
        # which only works from the main thread. We monkey-patch this to a
        # no-op since we're in daemon mode anyway and don't need the RNS
        # signal handlers overriding our process-level handlers.
        def _do_start():
            _log_info("Startup thread started")
            try:
                import RNS
                RNS.loglevel = getattr(RNS, "LOG_DEBUG", 0) if os.environ.get("NVA_VERBOSE") else 0
                RNS.logdest = RNS.LOG_STDOUT

                # Patch signal.signal for the duration of RNS init — it
                # requires the main thread, and we're in a background thread.
                # In daemon mode the signal handlers aren't critical.
                import signal as _signal_module
                _orig_signal = _signal_module.signal
                def _safe_signal(signum, handler):
                    try:
                        _orig_signal(signum, handler)
                    except ValueError:
                        _log_debug("signal.signal(%s, ...) skipped (not on main thread)", signum)
                _signal_module.signal = _safe_signal

                _log_debug("signal.signal patched for background thread")

                try:
                    from nomadnet_core.core.NomadNetworkApp import NomadNetworkApp

                    # Create a custom UIBackend that notifies Neovim
                    backend = _NeovimUIBackend(self)

                    _log_info("Creating NomadNetworkApp (this may take a while during Reticulum init)...")
                    app = NomadNetworkApp(
                        configdir=configdir,
                        rnsconfigdir=rnsconfigdir,
                        daemon=True,
                        ui_backend=backend,
                    )
                    _log_info("NomadNetworkApp created successfully")
                finally:
                    # Restore original signal.signal
                    _signal_module.signal = _orig_signal
                    _log_debug("signal.signal restored")

                # Hand results back to Neovim's main loop
                self.nvim.async_call(lambda: self._on_startup_done(app))

            except Exception as e:
                self.nvim.async_call(lambda e=e: self._on_startup_error(e))

        thread = threading.Thread(target=_do_start, daemon=True)
        thread.start()

    def _on_startup_done(self, app):
        """Called on Neovim's main loop when startup succeeds."""
        _log_info("Startup completed successfully")
        self.app = app
        self._starting = False
        self._startup_error = None
        self._start_announce_cache_worker()
        self.nvim.command("lua require'nvim-nomadnet'.on_startup_complete()")
        self.nvim.out_write(
            f"NomadNet started. Identity: {app.identity}\n"
            f"Display name: {app.get_display_name()}\n"
        )

    def _on_startup_error(self, exc):
        """Called on Neovim's main loop when startup fails."""
        _init_log()
        _log.exception("Startup failed: %s", exc)
        self._starting = False
        self._startup_error = str(exc)
        self.nvim.err_write(f"Failed to start NomadNet: {exc}\n")
        traceback.print_exc()

    def _stop_nomadnet(self):
        if self.app is None and not self._starting:
            return
        self._starting = False
        if self.app is not None:
            # Call Reticulum exit handler to save state & clean up
            try:
                if hasattr(self.app, 'reticulum') and self.app.reticulum:
                    self.app.reticulum.exit_handler()
            except Exception:
                pass
            # Stop LXMF router
            try:
                if hasattr(self.app, 'lxmf') and self.app.lxmf:
                    self.app.lxmf.exit_handler()
            except Exception:
                pass
            self.app = None

        # Reset all known singletons so NomadNet can be restarted
        try:
            from nomadnet_core.core.NomadNetworkApp import NomadNetworkApp
            NomadNetworkApp._shared_instance = None
        except Exception:
            pass
        try:
            import RNS
            RNS.Reticulum._Reticulum__instance = None
            RNS.Transport.destinations = []
            RNS.Transport.destinations_map = {}
            RNS.Transport.control_destinations = []
            RNS.Transport.mgmt_destinations = []
        except Exception:
            pass

        try:
            self.nvim.command("lua require'nvim-nomadnet'.on_stop()")
            self.nvim.out_write("NomadNet stopped.\n")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────
    # Conversation API
    # ──────────────────────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────
    # Helper: check startup status
    # ──────────────────────────────────────────────────────────────

    def _check_ready(self):
        """Return None if ready, or an error string if not."""
        if self._starting:
            return "NomadNet is still starting up (initialising Reticulum network). Please wait..."
        if self._startup_error:
            return f"NomadNet failed to start: {self._startup_error}"
        if self.app is None:
            return "NomadNet not started. Use :NvaStart first."
        return None

    # ──────────────────────────────────────────────────────────────
    # Conversation API
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaConversations", sync=True)
    def get_conversations(self, args):
        """Return a list of all conversations.

        Each entry: [source_hash_hex, display_name, trust_level,
                      sort_name, unread_count, last_activity_timestamp, failed_count]
        """
        _log_rpc_start("NvaConversations")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaConversations", {"error": status})
                return {"error": status}
            from nomadnet_core.core.Conversation import Conversation
            result = Conversation.conversation_list(self.app)
            _log_rpc_end("NvaConversations", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaConversations", {"error": str(e)})
            return {"error": str(e)}

    @pynvim.function("NvaConversationMessages", sync=True)
    def get_conversation_messages(self, args):
        """Return messages for a conversation identified by source_hash_hex."""
        _log_rpc_start("NvaConversationMessages")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaConversationMessages", {"error": status})
                return {"error": status}
            if not args:
                _log_rpc_end("NvaConversationMessages", [])
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
            _log_rpc_end("NvaConversationMessages", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaConversationMessages", {"error": str(e)})
            return {"error": str(e)}

    @pynvim.function("NvaSendMessage", sync=False)
    def send_message(self, args):
        """Send a message to a conversation.

        Args:
            args[0]: source_hash_hex (str)
            args[1]: content (str)
            args[2]: title (str, optional)
        """
        status = self._check_ready()
        if status is not None:
            self.nvim.err_write(status + "\n")
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
        status = self._check_ready()
        if status is not None:
            return
        if not args:
            return
        self.app.mark_conversation_read(args[0])

    @pynvim.function("NvaDeleteConversation", sync=False)
    def delete_conversation(self, args):
        """Delete a conversation by source_hash_hex."""
        status = self._check_ready()
        if status is not None:
            return
        if not args:
            return
        from nomadnet_core.core.Conversation import Conversation
        Conversation.delete_conversation(args[0], self.app)

    # ──────────────────────────────────────────────────────────────
    # Network / Announce Stream
    # ──────────────────────────────────────────────────────────────

    # Cache for async network announce reads — updated periodically
    # by a background thread so sync=True reads never block.
    _announce_cache = None
    _announce_cache_lock = threading.Lock()

    def _refresh_announce_cache(self):
        """Background task: reads the announce stream and caches the result."""
        try:
            if self.app is None:
                return
            stream = self.app.directory.announce_stream
            result = []
            for entry in stream:
                ts, sh, ad, at = entry
                app_data_text = ad.decode("utf-8", errors="replace") if isinstance(ad, bytes) else str(ad)
                result.append((ts, sh.hex() if isinstance(sh, bytes) else sh, app_data_text, at))
            with self._announce_cache_lock:
                self._announce_cache = result
        except Exception:
            pass

    def _start_announce_cache_worker(self):
        """Start a background thread that keeps caches updated."""
        def _worker():
            while self.app is not None:
                try:
                    self._refresh_announce_cache()
                    self._refresh_directory_cache()
                    self._refresh_rrc_cache()
                except Exception:
                    pass
                time.sleep(5)
        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    @pynvim.function("NvaNetworkAnnounces", sync=True)
    def get_network_announces(self, args):
        """Return the announce stream (from cache, never blocks)."""
        _log_rpc_start("NvaNetworkAnnounces")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaNetworkAnnounces", {"error": status})
                return {"error": status}
            with self._announce_cache_lock:
                if self._announce_cache is not None:
                    _log_rpc_end("NvaNetworkAnnounces", self._announce_cache)
                    return self._announce_cache
            result = self._read_announce_stream()
            _log_rpc_end("NvaNetworkAnnounces", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaNetworkAnnounces", {"error": str(e)})
            return {"error": str(e)}

    def _read_announce_stream(self):
        """Directly read the announce stream (may block if RNS locks held)."""
        try:
            stream = self.app.directory.announce_stream
            result = []
            for entry in stream:
                ts, sh, ad, at = entry
                app_data_text = ad.decode("utf-8", errors="replace") if isinstance(ad, bytes) else str(ad)
                result.append((ts, sh.hex() if isinstance(sh, bytes) else sh, app_data_text, at))
            with self._announce_cache_lock:
                self._announce_cache = result
            return result
        except Exception as e:
            return {"error": f"Could not read announces: {e}"}

    @pynvim.function("NvaNodePages", sync=True)
    def get_node_pages(self, args):
        """Return list of pages served by a node (requires node to be running)."""
        _log_rpc_start("NvaNodePages")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaNodePages", {"error": status})
                return {"error": status}
            if self.app.node is None:
                _log_rpc_end("NvaNodePages", [])
                return []
            result = self.app.node.servedpages
            _log_rpc_end("NvaNodePages", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaNodePages", {"error": str(e)})
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────
    # Page Fetching (Browser Protocol)
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaFetchPage", sync=False)
    def fetch_page(self, args):
        """Fetch a page from a NomadNet node asynchronously.

        args[0]: URL in lxmf@<hash>/path or hash/path format.
        Schedules _on_page_callback when done.
        """
        _log_debug(">>> NvaFetchPage called, args=%s", args)
        status = self._check_ready()
        if status is not None:
            self.nvim.err_write(status + "\n")
            _log_debug("<<< NvaFetchPage skipped: %s", status)
            return
        if not args:
            _log_debug("<<< NvaFetchPage skipped: no args")
            return
        url = args[0]
        from nomadnet_core.protocol import PageFetcher
        fetcher = PageFetcher(self.app)

        def on_ready(content, meta):
            _log_debug("PageFetcher on_ready for %s (content=%d bytes)", url, len(content) if content else 0)
            self._notify_page_result(url, content, meta, None)

        def on_error(code, msg):
            _log_debug("PageFetcher on_error for %s: code=%s msg=%s", url, code, msg)
            self._notify_page_result(url, None, None, (code, msg))

        fetcher.on_page_ready(on_ready)
        fetcher.on_page_error(on_error)
        _log_debug("PageFetcher retrieve_url starting for %s", url)
        fetcher.retrieve_url(url)
        _log_debug("PageFetcher retrieve_url returned (async) for %s", url)

    def _notify_page_result(self, url, content, meta, error):
        """Send page fetch result to Neovim buffer."""
        if error:
            self.nvim.async_call(self.nvim.out_write,
                                 f"Page error for {url}: {error[1]}\n")
            self.nvim.async_call(self.nvim.command,
                                 f"echohl ErrorMsg | echo 'NomadNet: Page error - {error[1]}' | echohl None")
            return
        self.nvim.async_call(self._display_page, url, content, meta)

    def _display_page(self, url, content, meta):
        """Create a new buffer to display the fetched page content with styling.

        Micron markup is rendered to plain text. Formatting (bold, italic,
        colors, links) is applied via nvim_buf_set_extmark for proper
        Neovim-native highlighting.
        """
        import time as _time
        _t0 = _time.time()
        api = self.nvim.api

        # Render micron markup to plain text, links, and extmark data
        try:
            from python.micron_render import render_page
            lines, links, extmarks = render_page(content) if content else (["(empty page)"], [], [])
        except Exception:
            lines = (content or "(empty page)").split("\n")
            links = []
            extmarks = []
        _t1 = _time.time()
        _log_debug("_display_page: render_page took %.3fs, %d lines, %d links, %d extmarks",
                     _t1 - _t0, len(lines), len(links), len(extmarks))

        # Resolve relative links to absolute URLs
        resolved_links = []
        for row, cs, ce, target in links:
            resolved = self._resolve_url(url, target)
            resolved_links.append((row, cs, ce, resolved))

        buf = api.create_buf(False, True)
        api.buf_set_option(buf, "buftype", "nofile")
        api.buf_set_option(buf, "bufhidden", "wipe")
        api.buf_set_option(buf, "swapfile", False)
        api.buf_set_option(buf, "modified", False)
        api.buf_set_name(buf, f"nomadnet://{url}")

        api.buf_set_lines(buf, 0, -1, False, lines)
        api.buf_set_option(buf, "modified", False)
        api.buf_set_option(buf, "filetype", "nomadnet")
        _t2 = _time.time()
        _log_debug("_display_page: buf setup took %.3fs", _t2 - _t1)

        # Apply extmark highlighting (bold, italic, colors)
        ns_id = api.create_namespace("nomadnet_page")
        self._applied_ns = ns_id
        extmark_count = 0
        for row, cs, ce, hl_group in extmarks:
            if hl_group and cs < ce:
                try:
                    api.buf_set_extmark(buf, ns_id, row, cs,
                                        {"end_col": ce, "hl_group": hl_group})
                    extmark_count += 1
                except Exception:
                    pass  # skip invalid extmarks
        _t3 = _time.time()
        _log_debug("_display_page: applied %d/%d extmarks in %.3fs",
                     extmark_count, len(extmarks), _t3 - _t2)

        # Store link data as buffer variable for Lua access
        try:
            api.buf_set_var(buf, "nomadnet_links", resolved_links)
        except Exception:
            pass

        # Keymaps
        api.buf_set_keymap(buf, "n", "q",
                           ":bdelete<CR>",
                           {"noremap": True, "silent": True, "desc": "Close"})
        api.buf_set_keymap(buf, "n", "<CR>",
                           ":lua require'nvim-nomadnet'.open_page_link()<CR>",
                           {"noremap": True, "silent": True, "desc": "Open link"})
        api.buf_set_keymap(buf, "n", "<Tab>",
                           ":lua require'nvim-nomadnet'.next_page_link()<CR>",
                           {"noremap": True, "silent": True, "desc": "Next link"})

        _t4 = _time.time()
        api.set_current_buf(buf)
        _log_debug("_display_page: total %.3fs for %s", _time.time() - _t0, url)

    @staticmethod
    def _resolve_url(current_url, link_target):
        """Resolve a possibly-relative link target against the current URL."""
        if link_target.startswith("lxmf@") or link_target.startswith("LXMF@"):
            return link_target

        base = current_url
        if base.startswith("lxmf@") or base.startswith("LXMF@"):
            base = base[5:]

        if link_target.startswith(":/"):
            if "/" in base:
                node_hash = base.split("/")[0]
                return f"lxmf@{node_hash}{link_target[1:]}"
            return f"lxmf@{base}{link_target}"

        return link_target

    # ──────────────────────────────────────────────────────────────
    # Directory
    # ──────────────────────────────────────────────────────────────

    # Cache for directory entries
    _directory_cache = None
    _directory_cache_lock = threading.Lock()

    def _refresh_directory_cache(self):
        """Background: read directory entries and cache them."""
        try:
            if self.app is None:
                return
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
            with self._directory_cache_lock:
                self._directory_cache = result
        except Exception:
            pass

    @pynvim.function("NvaDirectory", sync=True)
    def get_directory(self, args):
        """Return all directory entries (from cache, never blocks)."""
        _log_rpc_start("NvaDirectory")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaDirectory", {"error": status})
                return {"error": status}
            with self._directory_cache_lock:
                if self._directory_cache is not None:
                    _log_rpc_end("NvaDirectory", self._directory_cache)
                    return self._directory_cache
            result = self._read_directory()
            _log_rpc_end("NvaDirectory", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaDirectory", {"error": str(e)})
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────
    # RRC Channels
    # ──────────────────────────────────────────────────────────────

    def _read_directory(self):
        """Direct directory read (may block if RNS locks held)."""
        try:
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
            with self._directory_cache_lock:
                self._directory_cache = result
            return result
        except Exception as e:
            return {"error": f"Could not read directory: {e}"}

    # Cache for RRC channels
    _rrc_cache = None
    _rrc_cache_lock = threading.Lock()

    def _refresh_rrc_cache(self):
        """Background: read RRC hubs and cache them."""
        try:
            if self.app is None or self.app.rrc is None:
                return
            result = []
            for hub in self.app.rrc.hubs:
                result.append({
                    "hash": hub.hub_hash.hex() if isinstance(hub.hub_hash, bytes) else hub.hub_hash,
                    "name": hub.name,
                    "dest_name": hub.dest_name,
                    "rooms": list(hub.rooms),
                    "auto_reconnect": hub.auto_reconnect,
                })
            with self._rrc_cache_lock:
                self._rrc_cache = result
        except Exception:
            pass

    @pynvim.function("NvaRRCChannels", sync=True)
    def get_rrc_channels(self, args):
        """Return RRC hub list (from cache, never blocks)."""
        _log_rpc_start("NvaRRCChannels")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaRRCChannels", {"error": status})
                return {"error": status}
            with self._rrc_cache_lock:
                if self._rrc_cache is not None:
                    _log_rpc_end("NvaRRCChannels", self._rrc_cache)
                    return self._rrc_cache
            result = self._read_rrc_channels()
            _log_rpc_end("NvaRRCChannels", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaRRCChannels", {"error": str(e)})
            return {"error": str(e)}

    def _read_rrc_channels(self):
        """Direct RRC channel read (may block if RNS locks held)."""
        try:
            if self.app.rrc is None:
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
            with self._rrc_cache_lock:
                self._rrc_cache = result
            return result
        except Exception as e:
            return {"error": f"Could not read RRC channels: {e}"}

    @pynvim.function("NvaRRCMessages", sync=True)
    def get_rrc_messages(self, args):
        """Return messages for a given hub hash (hex)."""
        _log_rpc_start("NvaRRCMessages")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaRRCMessages", {"error": status})
                return {"error": status}
            if self.app.rrc is None or not args:
                _log_rpc_end("NvaRRCMessages", [])
                return []
            hub_hash_hex = args[0]
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
                    _log_rpc_end("NvaRRCMessages", msgs)
                    return msgs
            _log_rpc_end("NvaRRCMessages", [])
            return []
        except Exception as e:
            _log_rpc_end("NvaRRCMessages", {"error": str(e)})
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────
    # LXMF Sync
    # ──────────────────────────────────────────────────────────────

    @pynvim.command("NvaSync", sync=False)
    def cmd_sync(self):
        """Request LXMF sync from propagation node."""
        status = self._check_ready()
        if status is not None:
            self.nvim.err_write(status + "\n")
            return
        self.app.request_lxmf_sync()
        self.nvim.out_write("LXMF sync requested.\n")

    @pynvim.function("NvaSyncStatus", sync=True)
    def get_sync_status(self, args):
        """Return the current sync status string and progress."""
        _log_rpc_start("NvaSyncStatus")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaSyncStatus", (status, 0))
                return (status, 0)
            result = (self.app.get_sync_status(), self.app.get_sync_progress())
            _log_rpc_end("NvaSyncStatus", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaSyncStatus", {"error": str(e)})
            return (str(e), 0)

    # ──────────────────────────────────────────────────────────────
    # Directory Management
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaAddToDirectory", sync=True)
    def add_to_directory(self, args):
        """Add a peer/node to the directory by source hash.

        Args:
            args[0]: source_hash_hex (str) — required
            args[1]: display_name (str, optional) — if omitted, uses the hex hash
        """
        _log_rpc_start("NvaAddToDirectory")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaAddToDirectory", {"error": status})
                return {"error": status}
            if not args:
                _log_rpc_end("NvaAddToDirectory", {"error": "No hash provided"})
                return {"error": "No hash provided"}

            source_hash_hex = args[0]
            display_name = args[1] if len(args) > 1 else None

            # Decode hex hash to bytes
            try:
                source_hash = bytes.fromhex(source_hash_hex)
            except Exception:
                _log_rpc_end("NvaAddToDirectory", {"error": "Invalid hash (not valid hex)"})
                return {"error": "Invalid hash (not valid hex)"}

            # Check if already in directory
            from nomadnet_core.core.Directory import DirectoryEntry
            existing = self.app.directory.find(source_hash)
            if existing:
                _log_rpc_end("NvaAddToDirectory", {"info": "Already in directory"})
                return {"info": "Already in directory"}

            # Create entry and remember it
            entry = DirectoryEntry(
                source_hash,
                display_name=display_name or ("<" + source_hash_hex + ">"),
                trust_level=DirectoryEntry.UNKNOWN,
                hosts_node=False,
            )
            self.app.directory.remember(entry)
            _log_info("Added %s to directory (name=%s)", source_hash_hex, display_name)
            _log_rpc_end("NvaAddToDirectory", {"ok": True})
            return {"ok": True}

        except Exception as e:
            _log_rpc_end("NvaAddToDirectory", {"error": str(e)})
            return {"error": str(e)}

    @pynvim.function("NvaRemoveFromDirectory", sync=True)
    def remove_from_directory(self, args):
        """Remove a peer/node from the directory by source hash.

        Args:
            args[0]: source_hash_hex (str) — required
        """
        _log_rpc_start("NvaRemoveFromDirectory")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaRemoveFromDirectory", {"error": status})
                return {"error": status}
            if not args:
                _log_rpc_end("NvaRemoveFromDirectory", {"error": "No hash provided"})
                return {"error": "No hash provided"}

            source_hash_hex = args[0]
            try:
                source_hash = bytes.fromhex(source_hash_hex)
            except Exception:
                _log_rpc_end("NvaRemoveFromDirectory", {"error": "Invalid hash (not valid hex)"})
                return {"error": "Invalid hash (not valid hex)"}

            self.app.directory.forget(source_hash)
            _log_info("Removed %s from directory", source_hash_hex)
            _log_rpc_end("NvaRemoveFromDirectory", {"ok": True})
            return {"ok": True}

        except Exception as e:
            _log_rpc_end("NvaRemoveFromDirectory", {"error": str(e)})
            return {"error": str(e)}

    # ──────────────────────────────────────────────────────────────
    # Identity / Info
    # ──────────────────────────────────────────────────────────────

    @pynvim.function("NvaIdentity", sync=True)
    def get_identity(self, args):
        """Return identity info: [hash_hex, display_name]."""
        _log_rpc_start("NvaIdentity")
        try:
            status = self._check_ready()
            if status is not None:
                _log_rpc_end("NvaIdentity", [None, None, status])
                return [None, None, status]
            import RNS
            result = [
                RNS.hexrep(self.app.identity.hash, delimit=False),
                self.app.get_display_name(),
            ]
            _log_rpc_end("NvaIdentity", result)
            return result
        except Exception as e:
            _log_rpc_end("NvaIdentity", {"error": str(e)})
            return [None, None, str(e)]

    @pynvim.function("NvaSetDisplayName", sync=False)
    def set_display_name(self, args):
        """Set the display name."""
        status = self._check_ready()
        if status is not None:
            return
        if args:
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
