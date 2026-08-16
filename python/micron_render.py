"""
micron_render.py — Render NomadNet micron markup in Neovim.

Provides:
  micron_to_ansi(markup)       → str with ANSI escape codes
  micron_to_plain(markup)      → str with all markup stripped
  micron_to_extmarks(markup)   → (plain_text, [(row, col_start, col_end, group), ...])

The extmark output is designed for nvim_buf_set_extmark().
Highlight groups are defined in the nomadnet filetype plugin.
"""

import re
import time

# ── ANSI helpers ──────────────────────────────────────────────────

ANSI_RESET = "\033[0m"

# Map 3-hex RGB to ANSI color names
RGB_TO_ANSI_NAME = {
    (0,0,0): "black",     (1,0,0): "dark red",
    (0,1,0): "dark green", (1,1,0): "brown",
    (0,0,1): "dark blue",  (1,0,1): "dark magenta",
    (0,1,1): "dark cyan",  (2,2,2): "light gray",
    (3,3,3): "dark gray",  (5,0,0): "light red",
    (0,5,0): "light green", (5,5,0): "yellow",
    (0,0,5): "light blue",  (5,0,5): "light magenta",
    (0,5,5): "light cyan",  (5,5,5): "white",
}

ANSI_FG = { name: code for name, code in [
    ("black",30),("dark red",31),("dark green",32),("brown",33),
    ("dark blue",34),("dark magenta",35),("dark cyan",36),("light gray",37),
    ("dark gray",90),("light red",91),("light green",92),("yellow",93),
    ("light blue",94),("light magenta",95),("light cyan",96),("white",97),
]}
ANSI_BG = { name: code+10 for name, code in ANSI_FG.items() }


def _hex3_to_rgb5(s):
    """'f80' -> (15, 8, 0)  # 0-15 scale"""
    return (int(s[0],16)<<1 | int(s[0],16)>>3,
            int(s[1],16)<<1 | int(s[1],16)>>3,
            int(s[2],16)<<1 | int(s[2],16)>>3)

def _hex6_to_rgb5(s):
    """'ff8800' -> (15, 8, 0)"""
    return (int(s[0:2],16)>>4, int(s[2:4],16)>>4, int(s[4:6],16)>>4)

def _nearest_name(r, g, b):
    """(15,8,0) -> 'brown'  (nearest ANSI color name)"""
    def sqdist(c):
        return (c[0]-r)**2 + (c[1]-g)**2 + (c[2]-b)**2
    return RGB_TO_ANSI_NAME[min(RGB_TO_ANSI_NAME, key=sqdist)]

def _escape_fg(color):
    if len(color) == 6:
        r, g, b = _hex6_to_rgb5(color)
    else:
        r, g, b = _hex3_to_rgb5(color)
    return f"\033[{ANSI_FG[_nearest_name(r,g,b)]}m"

def _escape_bg(color):
    if len(color) == 6:
        r, g, b = _hex6_to_rgb5(color)
    else:
        r, g, b = _hex3_to_rgb5(color)
    return f"\033[{ANSI_BG[_nearest_name(r,g,b)]}m"

def _build_ansi(bold=False, italic=False, underline=False, fg=None, bg=None):
    parts = []
    if bold:      parts.append("1")
    if italic:    parts.append("3")
    if underline: parts.append("4")
    if fg:
        if len(fg) == 6: r,g,b = _hex6_to_rgb5(fg)
        else:            r,g,b = _hex3_to_rgb5(fg)
        parts.append(str(ANSI_FG[_nearest_name(r,g,b)]))
    if bg:
        if len(bg) == 6: r,g,b = _hex6_to_rgb5(bg)
        else:            r,g,b = _hex3_to_rgb5(bg)
        parts.append(str(ANSI_BG[_nearest_name(r,g,b)]))
    return f"\033[{';'.join(parts)}m" if parts else ""

# ── ANSI Renderer ─────────────────────────────────────────────────

class AnsiRenderer:
    """Stateful micron → ANSI converter."""

    def __init__(self):
        self.fg = None
        self.bg = None
        self.bold = False
        self.italic = False
        self.underline = False
        self.literal = False

    def _ansi(self):
        return _build_ansi(self.bold, self.italic, self.underline, self.fg, self.bg)

    def reset(self):
        self.__init__()

    def render(self, markup):
        self.reset()
        lines = markup.split("\n")
        out = []
        for line in lines:
            out.append(self._process_line(line))
        return "\n".join(out)

    def _process_line(self, raw):
        if self.literal:
            if raw.strip() == "`=":
                self.literal = False
                return ""
            return raw

        if raw.strip().startswith("#"):
            return ""

        if raw.strip() == "`=":
            self.literal = True
            return ""

        i = 0
        result = ""
        while i < len(raw):
            ch = raw[i]
            if ch == "`" and i+1 < len(raw):
                tag = raw[i+1]
                if tag == "[":
                    # Link: [label`url`...]
                    i += 2
                    depth = 1
                    start = i
                    while i < len(raw) and depth > 0:
                        if raw[i] == "[": depth += 1
                        elif raw[i] == "]": depth -= 1
                        if depth > 0: i += 1
                    link_raw = raw[start:i]
                    # Skip closing ]
                    if i < len(raw) and raw[i] == "]":
                        i += 1
                    parts = link_raw.split("`", 1)
                    label = parts[0] if parts else link_raw
                    old_u = self.underline
                    self.underline = True
                    result += self._ansi() + label
                    self.underline = old_u
                    result += ANSI_RESET + self._ansi()
                elif tag == "!":
                    self.bold = not self.bold
                    result += self._ansi()
                    i += 1
                elif tag == "*":
                    self.italic = not self.italic
                    result += self._ansi()
                    i += 1
                elif tag == "_":
                    self.underline = not self.underline
                    result += self._ansi()
                    i += 1
                elif tag == "F":
                    if i+2 < len(raw) and raw[i+2] == "T":
                        color = raw[i+3:i+9]
                        skip = 8
                    else:
                        color = raw[i+2:i+5]
                        skip = 4
                    self.fg = color
                    result += self._ansi()
                    i += skip
                elif tag == "B":
                    if i+2 < len(raw) and raw[i+2] == "T":
                        color = raw[i+3:i+9]
                        skip = 8
                    else:
                        color = raw[i+2:i+5]
                        skip = 4
                    self.bg = color
                    result += self._ansi()
                    i += skip
                elif tag == "f":
                    self.fg = None
                    result += self._ansi()
                    i += 1
                elif tag == "b":
                    self.bg = None
                    result += self._ansi()
                    i += 1
                elif tag == "`":
                    self.fg = None
                    self.bg = None
                    self.bold = False
                    self.italic = False
                    self.underline = False
                    result += ANSI_RESET
                    i += 1
                elif tag in ("c", "l", "r", "a"):
                    i += 1  # alignment - no visual effect
                elif tag == "<":
                    # Field input: `<flags|name`data>
                    close = raw.find("`>", i+1)
                    if close != -1:
                        # Just show field name as placeholder
                        field = raw[i+2:close]
                        fname = field.split("|")[-1] if "|" in field else field
                        old_u = self.underline
                        self.underline = True
                        result += self._ansi() + f"[{fname}]"
                        self.underline = old_u
                        result += ANSI_RESET + self._ansi()
                        i = close + 1
                    else:
                        result += ch
                elif tag == ">":
                    i += 1  # field end
                elif tag == "{":
                    # Partial `{hash:/path`...}
                    close = raw.find("}", i+1)
                    if close != -1:
                        i = close
                    else:
                        result += ch
                elif tag == ":":
                    # Anchor `:name
                    while i+1 < len(raw) and (raw[i+1].isalnum() or raw[i+1] in "_-"):
                        i += 1
                elif tag == "=":
                    # Literal toggle - already handled upstream
                    i += 1
                elif tag == "<":
                    i += 1
                else:
                    result += tag
                    i += 1
            else:
                result += ch
            i += 1

        return result


def micron_to_ansi(markup):
    """Convert micron markup to ANSI-escaped text."""
    return AnsiRenderer().render(markup)


# ── Plain text renderer ───────────────────────────────────────────

def micron_to_plain(markup):
    """Strip micron tags and return plain text."""
    text = markup

    # 1. Remove partials `{...}
    text = re.sub(r'`\{[^}]*\}', '', text)

    # 2. Convert links: `[label`url`...] -> label
    text = re.sub(r'`\[([^]]*?)(?:`[^]]*?)*\]', r'\1', text)

    # 3. Remove remaining ` tags (formatting, colors, etc.)
    text = re.sub(r'`[FB]T[0-9a-fA-F]{6}', '', text)
    text = re.sub(r'`[FB][0-9a-fA-F]{3}', '', text)
    text = re.sub(r'`[!*_=fbacrl`<>{:]+', '', text)

    # 4. Remove comment lines
    lines = []
    for line in text.split("\n"):
        if not line.strip().startswith("#"):
            lines.append(line)
    return "\n".join(lines)


# ── Extmark renderer (for nvim_buf_set_extmark) ──────────────────

# Neovim highlight group names
HL_NOMADNET_KEYWORD  = "NomadNetKeyword"
HL_NOMADNET_LINK     = "NomadNetLink"
HL_NOMADNET_FIELD    = "NomadNetField"
HL_NOMADNET_HEADING  = "NomadNetHeading"
HL_NOMADNET_DIVIDER  = "NomadNetDivider"
HL_NOMADNET_BOLD     = "NomadNetBold"
HL_NOMADNET_ITALIC   = "NomadNetItalic"
HL_NOMADNET_UNDERLINE = "NomadNetUnderline"
HL_NOMADNET_COMMENT  = "NomadNetComment"


import logging as _extract_log
_extract_logger = _extract_log.getLogger("nvim-nomadnet")

def extract_links(markup):
    """Parse micron markup and extract hyperlinks with their positions.

    Returns:
        plain_lines: list of str, one per line of rendered text
        links: list of (row, col_start, col_end, url) tuples
    """
    _start_time = time.time()
    lines = markup.split('\n')
    plain_lines = []
    links = []

    for row, line in enumerate(lines):
        # Safety watchdog: abort if a single line takes >1 second
        if row > 0 and row % 50 == 0 and time.time() - _start_time > 2:
            _extract_logger.warning(
                "extract_links aborting after %.1fs at line %d/%d (%d chars)",
                time.time() - _start_time, row, len(lines), len(line))
            break
        # Skip comment-only lines
        stripped_line = line.strip()
        if stripped_line.startswith('#'):
            plain_lines.append('')
            continue

        # Handle literal blocks
        if stripped_line == '`=':
            plain_lines.append('')
            continue

        plain = ""
        i = 0
        _line_iters = 0
        while i < len(line):
            _line_iters += 1
            if _line_iters > 100000:
                _extract_logger.warning("extract_links: line %d exceeded 100K iterations, aborting line", row)
                break
            c = line[i]
            if c == '`' and i + 1 < len(line):
                nxt = line[i + 1]

                if nxt == '[':
                    # Link: `[label`url`fields] or `[label`url] or `[label]
                    i += 2
                    depth = 1
                    content_start = i
                    while i < len(line) and depth > 0:
                        if line[i] == '[':
                            depth += 1
                        elif line[i] == ']':
                            depth -= 1
                        if depth > 0:
                            i += 1
                    link_raw = line[content_start:i]
                    i += 1  # skip closing ]

                    parts = link_raw.split('`', 2)
                    label = parts[0]
                    url = parts[1] if len(parts) > 1 else label

                    col_start = len(plain)
                    plain += label
                    links.append((row, col_start, len(plain), url))
                    continue  # skip the i += 1

                elif nxt == 'F':
                    # `F + 3 hex chars OR `FT + 6 hex chars
                    # Total tag length: 1(`)+1(F)+3(hex)=5 or 1+2(FT)+6=9
                    if i + 2 < len(line) and line[i + 2] == 'T':
                        i += 9
                    else:
                        i += 5
                    continue
                elif nxt == 'B':
                    if i + 2 < len(line) and line[i + 2] == 'T':
                        i += 9
                    else:
                        i += 5
                    continue
                elif nxt in ('!', '*', '_', 'f', 'b', '`', 'c', 'l', 'r', 'a'):
                    i += 2  # skip ` + tag char
                    continue
                elif nxt == '{':
                    close = line.find('}', i + 1)
                    if close != -1:
                        i = close + 1
                    else:
                        i += 2
                    continue
                elif nxt == '<':
                    close = line.find('`>', i + 1)
                    if close != -1:
                        i = close + 2
                    else:
                        i += 2
                    continue
                elif nxt == '>':
                    i += 2
                    continue
                elif nxt == ':':
                    # Anchor
                    i += 2
                    while i < len(line) and (line[i].isalnum() or line[i] in '_-'):
                        i += 1
                    continue
                elif nxt == '=':
                    # Literal toggle (multi-line, handled per-line)
                    i += 2
                    continue
                else:
                    # Unknown tag — output the backtick and advance
                    plain += c
                    i += 1
                    continue
            elif c == '#' and (i == 0 or line[:i].strip() == ''):
                # Comment at start of line — skip rest
                break
            else:
                plain += c
                i += 1

        plain_lines.append(plain)

    return plain_lines, links


# ── Extmark renderer ──────────────────────────────────────────────

class ExtmarkRenderer:
    """Stateful micron → (plain_text, extmarks) converter.

    Each extmark is: (row, col_start, col_end, highlight_group)
    where highlight_group is a string name for nvim_buf_set_extmark's
    `hl_group` option.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.fg = None        # 3 or 6 hex string
        self.bg = None        # 3 or 6 hex string
        self.bold = False
        self.italic = False
        self.underline = False
        self.literal = False
        self.extmarks = []    # accumulated across lines
        self.result_lines = []  # plain text lines
        self._active_span = None  # (group, start_col) of active span, or None
        self._current_row = 0    # current line being processed

    def _start_span(self, col):
        """Begin a new highlight span at the given column.
        Flushes any active span first."""
        self._flush_span(col)
        group = self._style_group()
        if group:
            self._active_span = (group, col)

    def _flush_span(self, end_col):
        """Emit the current highlight span and close it."""
        if self._active_span is not None:
            group, start = self._active_span
            self._active_span = None
            if start < end_col:
                self.extmarks.append((self._current_row, start, end_col, group))

    def _end_line(self):
        """Flush any active span at end of line."""
        line_len = len(self.result_lines[-1]) if self.result_lines else 0
        self._flush_span(line_len)
        # Don't carry over a fg/bg color span to the next empty line
        # if the current line is empty — stale spans on blank lines
        # produce extmarks that highlight nothing.
        if line_len == 0:
            self._active_span = None

    @staticmethod
    def _ansi_to_cterm(esc):
        """Convert an ANSI escape code (30-37, 90-97) to a ctermfg index (0-15)."""
        if 30 <= esc <= 37:
            return esc - 30      # 0-7
        elif 90 <= esc <= 97:
            return esc - 82      # 8-15
        return esc               # fallback

    @classmethod
    def _color_group(cls, hex_color, prefix):
        """Map a 3 or 6 hex color to NomadNetFG{N:03d} or NomadNetBG{N:03d}.

        The suffix N is the ctermfg/ctermbg index (0-15), matching the
        NomadNetFG000-NomadNetFG015 / NomadNetBG000-NomadNetBG015 groups
        defined in after/ftplugin/nomadnet.vim.
        """
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16) >> 4
            g = int(hex_color[2:4], 16) >> 4
            b = int(hex_color[4:6], 16) >> 4
        else:
            r = int(hex_color[0], 16) << 1 | int(hex_color[0], 16) >> 3
            g = int(hex_color[1], 16) << 1 | int(hex_color[1], 16) >> 3
            b = int(hex_color[2], 16) << 1 | int(hex_color[2], 16) >> 3
        name = _nearest_name(r, g, b)
        esc = ANSI_FG.get(name, 7)
        idx = cls._ansi_to_cterm(esc)
        return f"{prefix}{idx:03d}"

    def _style_group(self):
        """Return a highlight group name for the current style/color state.

        Returns the most specific non-None group. Prioritizes:
        bold > italic > underline > fg color > bg color.
        """
        if self.bold:
            return HL_NOMADNET_BOLD
        if self.italic:
            return HL_NOMADNET_ITALIC
        if self.underline:
            return HL_NOMADNET_UNDERLINE
        if self.fg:
            return self._color_group(self.fg, "NomadNetFG")
        if self.bg:
            return self._color_group(self.bg, "NomadNetBG")
        return None

    def render(self, markup):
        """Convert micron markup to (plain_lines, extmarks).

        Returns:
            plain_lines: list of str
            extmarks: list of (row, col_start, col_end, hl_group)
        """
        self.reset()
        for line in markup.split("\n"):
            self._process_line(line)
        return self.result_lines, self.extmarks

    def _process_line(self, raw):
        self._current_row = len(self.result_lines)
        # If there's an active style from a previous line, start a new span
        # at the beginning of this line so the color/formatting carries over.
        group = self._style_group()
        if group:
            self._active_span = (group, 0)
        plain = ""

        if self.literal:
            if raw.strip() == "`=":
                self.literal = False
                self.result_lines.append("")
                return
            self.result_lines.append(raw)
            return

        if raw.strip().startswith("#"):
            self.result_lines.append("")
            return

        if raw.strip() == "`=":
            self.literal = True
            self.result_lines.append("")
            return

        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch == "`" and i + 1 < len(raw):
                tag = raw[i + 1]

                if tag == "[":
                    # Link: `[label`url`...]
                    i += 2
                    depth = 1
                    start = i
                    while i < len(raw) and depth > 0:
                        if raw[i] == "[":
                            depth += 1
                        elif raw[i] == "]":
                            depth -= 1
                        if depth > 0:
                            i += 1
                    link_raw = raw[start:i]
                    # Skip the closing ] so it doesn't leak into plain text
                    if i < len(raw) and raw[i] == "]":
                        i += 1
                    parts = link_raw.split("`", 1)
                    label = parts[0] if parts else link_raw
                    col_start = len(plain)
                    # Flush any active style and start link span
                    self._flush_span(col_start)
                    plain += label
                    # Emit link extmark for the label text
                    if col_start < len(plain):
                        self.extmarks.append((self._current_row, col_start, len(plain), HL_NOMADNET_LINK))
                    # Restore any style after link
                    self._start_span(len(plain))
                    continue

                elif tag == "!":
                    self.bold = not self.bold
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag == "*":
                    self.italic = not self.italic
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag == "_":
                    self.underline = not self.underline
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag == "F":
                    if i + 2 < len(raw) and raw[i + 2] == "T":
                        self.fg = raw[i + 3:i + 9]
                        skip = 8
                    else:
                        self.fg = raw[i + 2:i + 5]
                        skip = 4
                    col = len(plain)
                    self._start_span(col)
                    i += skip  # skip 4 or 8 chars including backtick, then outer i+=1 makes it skip+1

                elif tag == "B":
                    if i + 2 < len(raw) and raw[i + 2] == "T":
                        self.bg = raw[i + 3:i + 9]
                        skip = 8
                    else:
                        self.bg = raw[i + 2:i + 5]
                        skip = 4
                    col = len(plain)
                    self._start_span(col)
                    i += skip  # skip 4 or 8 chars including backtick, then outer i+=1 makes it skip+1

                elif tag == "f":
                    self.fg = None
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag == "b":
                    self.bg = None
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag == "`":
                    self.fg = None
                    self.bg = None
                    self.bold = False
                    self.italic = False
                    self.underline = False
                    i += 1
                    col = len(plain)
                    self._start_span(col)

                elif tag in ("c", "l", "r", "a"):
                    i += 1  # alignment — no visual effect

                elif tag == "{":
                    # Partial `{hash:/path`...}
                    close = raw.find("}", i + 1)
                    if close != -1:
                        i = close
                    else:
                        plain += ch
                    i += 1

                elif tag == ":":
                    # Anchor `:name
                    i += 2
                    while i + 1 < len(raw) and (raw[i + 1].isalnum() or raw[i + 1] in "_-"):
                        i += 1

                elif tag == "=":
                    i += 1  # literal toggle (handled per-line)

                elif tag == "<":
                    # Field input: `<flags|name`data>
                    close = raw.find("`>", i + 1)
                    if close != -1:
                        field = raw[i + 2:close]
                        fname = field.split("|")[-1] if "|" in field else field
                        col_start = len(plain)
                        self._flush_span(col_start)
                        plain += f"[{fname}]"
                        self.extmarks.append((self._current_row, col_start, len(plain), HL_NOMADNET_FIELD))
                        self._start_span(len(plain))
                        i = close + 1
                    else:
                        plain += ch

                elif tag == ">":
                    i += 1  # field end — no visual

                else:
                    plain += tag
            else:
                plain += ch
            i += 1

        self.result_lines.append(plain)
        self._end_line()


def micron_to_extmarks(markup):
    """Convert micron markup to (plain_lines, extmarks) for nvim_buf_set_extmark.

    Returns:
        plain_lines: list of str, one per rendered line
        extmarks: list of (row, col_start, col_end, hl_group_name)
    """
    return ExtmarkRenderer().render(markup)


def render_page(markup):
    """Full page rendering: plain text + link metadata + extmarks.

    Returns (plain_lines, links, extmarks) suitable for Neovim display
    with nvim_buf_set_extmark highlighting.

    Uses ExtmarkRenderer as the single source of plain text, then
    extracts link information separately.
    """
    # Use ExtmarkRenderer as the canonical source of plain lines so
    # extmarks always align with the displayed text.
    renderer = ExtmarkRenderer()
    plain_lines, extmarks = renderer.render(markup)
    _, links = extract_links(markup)
    return plain_lines, links, extmarks


# ── Debug helper ──────────────────────────────────────────────────

if __name__ == "__main__":
    sample = (
        "`!Heading`!\n\n"
        "`FaaaNormal text\n\n"
        "`[Cypherpunk`:/page/cypherpunk.mu] | `[Bitcoin`:/page/bitcoin.mu]\n"
        "\n"
        "`!Welcome`!\n"
        "\n"
        "Visit `[our chat`:/page/chat/chat.mu]\n"
    )
    print("=== ANSI output ===")
    print(repr(micron_to_ansi(sample)))
    print()
    print("=== Links ===")
    lines, links = extract_links(sample)
    for row, cs, ce, url in links:
        print(f"  [{row}:{cs}-{ce}] '{lines[row][cs:ce]}' -> {url}")
    print()
    print("=== Plain text ===")
    for i, l in enumerate(lines):
        print(f"  [{i}] {l}")
