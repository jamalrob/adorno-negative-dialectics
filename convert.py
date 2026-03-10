#!/usr/bin/env python3
"""Convert Adorno Negative Dialectics (Redmond 2001) PDF to navigable HTML.

Usage: python3 convert.py
Output: content/negative-dialectics.html
"""

import re
import subprocess
from html import escape
from pathlib import Path

PDF_PATH = (
    Path(__file__).parent
    / "assets"
    / "adorno-theodor-negative-dialectics-2019-dennis-redmond-translation.pdf"
)
OUT_PATH = Path(__file__).parent / "negative-dialectics.html"

# ── Feature flags ──────────────────────────────────────────────────────────────

HYPOTHESIS = False  # Set to True to include the Hypothesis annotation embed

# ── Heading registries ────────────────────────────────────────────────────────

KNOWN_H1 = {
    "Translator's Notes": "translators-notes",
    "Editor\u2019s Note": "editors-note",   # PDF uses Unicode right-single-quote
    "Prologue": "prologue",
    "Introduction": "introduction",
    "Part I: Relationship to Ontology": "part-i",
    "Part II: Negative Dialectics: Concept and Categories": "part-ii",
    "Part III: Models": "part-iii",
    "Endnotes": "endnotes",
}

# Endnotes sub-headings (ALL CAPS but different from body h3s)
KNOWN_ENDNOTE_H3 = {
    "INTRODUCTION": "endnote-introduction",
    "PART I, SECTION I: THE ONTOLOGICAL NEED": "endnote-part-i-i",
    "PART I, SECTION II: BEING AND EXISTENCE": "endnote-part-i-ii",
    "PART II: NEGATIVE DIALECTICS, CONCEPT AND CATEGORIES": "endnote-part-ii",
    "PART III: MODELS, SECTION I: FREEDOM": "endnote-part-iii-i",
    "PART III: MODELS, SECTION II: WORLD-SPIRIT AND NATURAL HISTORY": (
        "endnote-part-iii-ii"
    ),
    "PART III: MODELS, SECTION III: MEDITATIONS ON METAPHYSICS": (
        "endnote-part-iii-iii"
    ),
}

KNOWN_H2 = {
    "I. The Ontological Need": "the-ontological-need",
    "II. Being and Existence": "being-and-existence",
    "I. Freedom: Metacritique of Practical Reason": "freedom",
    "II. World-spirit and Natural History: Excursus on Hegel": (
        "world-spirit-and-natural-history"
    ),
    "III. Meditations on Metaphysics": "meditations-on-metaphysics",
}

ALL_KNOWN = {**KNOWN_H1, **KNOWN_H2, **KNOWN_ENDNOTE_H3}

# Maps body section anchor IDs → endnote section anchor IDs.
# Consumed by both the JS generator and any future Python tooling.
SECTION_TO_ENDNOTE = {
    "introduction":                     "endnote-introduction",
    "the-ontological-need":             "endnote-part-i-i",
    "being-and-existence":              "endnote-part-i-ii",
    "part-ii":                          "endnote-part-ii",
    "freedom":                          "endnote-part-iii-i",
    "world-spirit-and-natural-history": "endnote-part-iii-ii",
    "meditations-on-metaphysics":       "endnote-part-iii-iii",
}

# Lines that look like ALL CAPS headings but are actually signatures/attributions
KNOWN_NOT_HEADINGS = {"THEODOR W. ADORNO"}

# ── Discussion links ───────────────────────────────────────────────────────────
# Loaded from discussion_links.yaml. Edit that file to add new entries.
# Format: section-anchor-id: [[Username, url], ...]
# Multiple posts by the same user are automatically numbered: Username (1), (2)…

import yaml as _yaml

_links_path = Path(__file__).parent / "discussion_links.yaml"
DISCUSSION_LINKS = {
    k: [tuple(pair) for pair in v]
    for k, v in _yaml.safe_load(_links_path.read_text()).items()
}

# ── Utilities ─────────────────────────────────────────────────────────────────


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", s)


FOOTNOTE_MARKER = "\x01"      # New asterisk footnote (line starts with *)
FOOTNOTE_CONT_MARKER = "\x02"  # Continuation of previous page's footnote


def is_page_number(s: str) -> bool:
    """True for standalone page numbers (arabic or roman, ≤ 5 chars)."""
    return bool(re.match(r"^[ivxlcdm\d]{1,5}$", s, re.IGNORECASE)) and len(s) <= 5


def ends_cleanly_unicode(line: str) -> bool:
    """True if line ends with terminal punctuation, including Unicode quotes."""
    s = line.rstrip()
    return s.endswith(('.', ')', ']', '"', "'", '\u201d', '\u2019', '!', '?'))


def _is_separator(s: str) -> bool:
    return bool(re.search(r'\.{5,}', s) or re.match(r'^[_\-]{3,}$', s))


def preprocess_footnotes(raw_text: str) -> str:
    """Mark in-page asterisk footnote lines with FOOTNOTE_MARKER, page by page.

    Handles:
    - New footnotes: lines starting with * at the bottom of a page
    - Multi-page continuations: the last paragraph block on a continuation page
    """
    pages = raw_text.split('\x0c')
    result_pages = []
    footnote_continues = False

    for page in pages:
        lines = page.split('\n')

        # Find page number line (search from end)
        pageno_idx = None
        for j in range(len(lines) - 1, -1, -1):
            if is_page_number(lines[j].strip()):
                pageno_idx = j
                break

        content = lines[:pageno_idx] if pageno_idx is not None else lines
        suffix = lines[pageno_idx:] if pageno_idx is not None else []

        # Find first line starting with * (new footnote)
        ast_idx = None
        for j, l in enumerate(content):
            if l.startswith('*'):
                ast_idx = j
                break

        if ast_idx is not None:
            # New footnote starts here: mark from * to end of content
            body_lines = content[:ast_idx]
            fn_lines = content[ast_idx:]
            new_content = body_lines + [FOOTNOTE_MARKER + l for l in fn_lines]

            # Check if footnote continues to next page
            last_fn = next(
                (l for l in reversed(fn_lines)
                 if l.strip() and not _is_separator(l.strip())),
                ''
            )
            footnote_continues = not ends_cleanly_unicode(last_fn.rstrip())

        elif footnote_continues:
            # Continuation page: the last paragraph block before the page number
            # is the footnote continuation.
            last_blank = None
            for j in range(len(content) - 1, -1, -1):
                if not content[j].strip():
                    last_blank = j
                    break

            if last_blank is not None:
                fn_candidate = content[last_blank + 1:]
                fn_content = [
                    l for l in fn_candidate
                    if l.strip() and not _is_separator(l.strip())
                ]
                if fn_content:
                    new_content = (
                        content[:last_blank + 1]
                        + [FOOTNOTE_CONT_MARKER + l for l in fn_candidate]
                    )
                    last_fn = fn_content[-1]
                    footnote_continues = not ends_cleanly_unicode(last_fn.rstrip())
                else:
                    new_content = content
                    footnote_continues = False
            else:
                new_content = content
                footnote_continues = False
        else:
            new_content = content
            footnote_continues = False

        result_pages.append('\n'.join(new_content + suffix))

    return '\x0c'.join(result_pages)


def strip_decorative(s: str) -> str:
    """Remove curly quotes, brackets and other punctuation for heading tests."""
    s = re.sub(r"[\u201c\u201d\u201e\u201f\u2018\u2019\"\'*]+", "", s)
    s = re.sub(r"\[.*?\]", "", s)
    return s.strip()


def is_all_caps_heading(s: str) -> bool:
    """True if s is an Adorno ALL CAPS subsection heading.

    Handles standard headings ("QUESTION AND ANSWER") and the numbered
    headings in Meditations on Metaphysics ("1 AFTER AUSCHWITZ").
    """
    stripped = s.strip()

    # Numbered Meditations heading: "1 AFTER AUSCHWITZ", '5 "NIHILISM"'
    m = re.match(r"^(\d{1,2})\s+([\u201c\u201d\"']?[A-Z].+)$", stripped)
    if m:
        rest = m.group(2)
        core = strip_decorative(rest)
        if len(core) > 3 and not any(c.islower() for c in core.replace(" ", "")):
            return True

    # Standard ALL CAPS heading
    if stripped in KNOWN_NOT_HEADINGS:
        return False
    core = strip_decorative(stripped)
    core = re.sub(r"\s+", " ", core).strip()
    if len(core) < 6 or len(stripped) > 100:
        return False
    allowed = set(" ,':.-/\u2013\u2014")
    return all(c.isupper() or c in allowed for c in core) and any(
        c.isupper() for c in core
    )


# ── Merge split headings ───────────────────────────────────────────────────────


def merge_split_headings(lines: list[str]) -> list[str]:
    """Join lines that were wrapped mid-heading by the PDF layout.

    e.g. "Part II: Negative Dialectics: Concept" + "and Categories"
         → "Part II: Negative Dialectics: Concept and Categories"
    """
    result = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # Is this line the start of a known heading that isn't complete?
        matched = None
        for heading in ALL_KNOWN:
            if (
                heading != stripped
                and heading.startswith(stripped)
                and len(stripped) > 8
            ):
                matched = heading
                break

        if matched:
            # Absorb subsequent non-blank, non-page-number lines until we
            # complete the heading or give up.
            collected = stripped
            j = i + 1
            while j < len(lines) and collected != matched:
                nxt = lines[j].strip()
                if not nxt or is_page_number(nxt):
                    j += 1
                    continue
                candidate = collected + " " + nxt
                if matched.startswith(candidate) or candidate == matched:
                    collected = candidate
                    j += 1
                else:
                    break

            if collected == matched:
                result.append(matched)
                i = j
            else:
                result.append(lines[i])
                i += 1
        else:
            result.append(lines[i])
            i += 1

    return result


# ── Parser ────────────────────────────────────────────────────────────────────


def parse(raw: str):
    """Yield (kind, text, anchor) tuples from the raw pdftotext output.

    kind ∈ {'h1', 'h2', 'h3', 'p', 'footnote', 'page'}
    """
    lines = [line.replace("\x0c", "").rstrip() for line in raw.split("\n")]

    # Remove page numbers and the blank lines immediately before them.
    # Whether to insert a replacement blank depends on what follows:
    # - next line has leading spaces (indented) → new paragraph, insert blank
    # - next line has 0 leading spaces → continuation, insert nothing
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if is_page_number(s):
            # Remove trailing blank lines already added
            while cleaned and not cleaned[-1].strip():
                cleaned.pop()
            # Look ahead to the next non-empty line
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                leading = len(lines[j]) - len(lines[j].lstrip())
                next_s = lines[j].strip()
                if leading >= 1 or is_all_caps_heading(next_s) or next_s in ALL_KNOWN:
                    cleaned.append("")   # new paragraph, heading, or known section follows
                # else: 0 leading spaces, plain text → continuation, no blank needed
            else:
                cleaned.append("")  # end of document, add blank for safety
            i += 1
        else:
            cleaned.append(line)
            i += 1
    lines = cleaned

    lines = merge_split_headings(lines)

    para: list[str] = []
    fn_para: list[str] = []
    in_footnote = False
    fn_is_cont = False  # True if current footnote block is a page continuation

    def flush():
        nonlocal para
        if para:
            yield ("p", " ".join(para), None)
            para = []

    def flush_fn():
        nonlocal fn_para, fn_is_cont
        if fn_para:
            kind = "footnote_cont" if fn_is_cont else "footnote"
            yield (kind, " ".join(fn_para), None)
            fn_para = []

    # Suppress everything before the first real h1 heading (title page + TOC)
    preamble = True
    in_endnotes = False
    done = False

    for line in lines:
        if done:
            break

        # Check for footnote markers BEFORE stripping (\x01 and \x02 are not whitespace)
        is_fn_line = line.startswith(FOOTNOTE_MARKER)
        is_fn_cont_line = line.startswith(FOOTNOTE_CONT_MARKER)
        if is_fn_line:
            s = line[len(FOOTNOTE_MARKER):].strip()
        elif is_fn_cont_line:
            s = line[len(FOOTNOTE_CONT_MARKER):].strip()
        else:
            s = line.strip()

        # ── blanks ──
        if not s:
            if in_footnote and (is_fn_line or is_fn_cont_line):
                # Blank line within footnote section — PDF layout artifact, skip it
                continue
            if in_footnote:
                yield from flush_fn()
                in_footnote = False
            else:
                yield from flush()
            continue

        # ── skip TOC dot-leader lines and footnote separators ──
        if re.search(r"\.{5,}", s) or re.match(r"^[_\-]{3,}$", s):
            continue

        # ── new footnote lines (start with *) ──
        if is_fn_line:
            if preamble:
                continue
            if not in_footnote:
                yield from flush()
                in_footnote = True
                fn_is_cont = False
            # Strip the leading * and whitespace from the first line
            text = s.lstrip("* ") if s.startswith("*") else s
            if text:
                fn_para.append(text)
            continue

        # ── footnote continuation lines (from next page's bottom) ──
        if is_fn_cont_line:
            if preamble:
                continue
            if not in_footnote:
                yield from flush()
                in_footnote = True
                fn_is_cont = True
            if s:
                fn_para.append(s)
            continue

        # ── switching back to body from footnote ──
        if in_footnote:
            yield from flush_fn()
            in_footnote = False
            fn_is_cont = False

        # ── known h1 ──
        if s == "Index":
            yield from flush()
            done = True
            break
        if s in KNOWN_H1:
            preamble = False
            in_endnotes = (s == "Endnotes")
            yield from flush()
            yield ("h1", s, KNOWN_H1[s])
            continue

        # ── known h2 ──
        if s in KNOWN_H2:
            yield from flush()
            yield ("h2", s, KNOWN_H2[s])
            continue

        # ── known endnote h3 (exact match after merge) ──
        if s in KNOWN_ENDNOTE_H3:
            yield from flush()
            yield ("h3", s, KNOWN_ENDNOTE_H3[s])
            continue

        # ── skip everything else while still in preamble ──
        if preamble:
            continue

        # ── ALL CAPS h3 — only valid when not already mid-paragraph ──
        if is_all_caps_heading(s) and not para:
            yield from flush()
            anchor = slugify(
                strip_decorative(s).lower().replace("  ", " ")
            )
            yield ("h3", s, anchor)
            continue

        # ── endnote numbered entries — each starts a new paragraph ──
        if in_endnotes and re.match(r"^\d+\.\s", s) and para:
            yield from flush()

        # ── body text ──
        para.append(s)

    yield from flush()
    if in_footnote:
        yield from flush_fn()


# ── HTML generation ───────────────────────────────────────────────────────────

CSS = """\
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #faf9f6;
  --text: #1a1a1a;
  --muted: #888;
  --accent: #5a3e2b;
  --toc-bg: #f2efe9;
  --toc-border: #d8d0c4;
  --toc-width: 280px;
  --page-marker: #bbb;
  --heading-color: #2c1a0e;
  --link: #5a3e2b;
}

/* Dark theme — applied by JS toggle or system preference */
[data-theme="dark"] {
  --bg: #1e2025;
  --text: #d6d8de;
  --muted: #6b7080;
  --accent: #7a90b8;
  --toc-bg: #18191e;
  --toc-border: #2c3040;
  --page-marker: #4a4d56;
  --heading-color: #a4aec4;
  --link: #7a90b8;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1e2025;
    --text: #d6d8de;
    --muted: #6b7080;
    --accent: #7a90b8;
    --toc-bg: #18191e;
    --toc-border: #2c3040;
    --page-marker: #4a4d56;
    --heading-color: #a4aec4;
    --link: #7a90b8;
  }
}

/* ── Theme toggle button ── */
#theme-toggle {
  display: block;
  width: 100%;
  margin-bottom: 1rem;
  padding: 0.3rem 0.5rem;
  background: none;
  border: 1px solid var(--toc-border);
  border-radius: 4px;
  color: var(--muted);
  font-family: system-ui, sans-serif;
  font-size: 0.72rem;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, color 0.15s;
}
#theme-toggle:hover { border-color: var(--link); color: var(--text); }
#mono-toggle {
  display: block;
  width: 100%;
  margin-bottom: 1rem;
  padding: 0.3rem 0.5rem;
  background: none;
  border: 1px solid var(--toc-border);
  border-radius: 4px;
  color: var(--muted);
  font-family: system-ui, sans-serif;
  font-size: 0.72rem;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, color 0.15s;
}
#mono-toggle:hover { border-color: var(--link); color: var(--text); }
#mono-toggle.active { border-color: var(--link); color: var(--text); }

[data-mono="true"] #content {
  font-family: 'JetBrains Mono', ui-monospace, Menlo, Consolas, 'Courier New', monospace;
}

html { font-size: 20px; scroll-behavior: smooth; }

body {
  display: flex;
  background: var(--bg);
  color: var(--text);
  font-family: 'Bitstream Charter', Charter, Georgia, serif;
  line-height: 1.75;
}

/* ── TOC sidebar ── */
#toc {
  position: sticky;
  top: 0;
  height: 100vh;
  width: var(--toc-width);
  flex-shrink: 0;
  overflow-y: auto;
  background: var(--toc-bg);
  border-right: 1px solid var(--toc-border);
  padding: 1.5rem 1rem;
  font-family: system-ui, sans-serif;
  font-size: 0.78rem;
}

#toc h2 {
  font-size: 0.7rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 1rem;
}

#toc ul { list-style: none; }
#toc li { margin: 0; }

#toc a {
  display: block;
  padding: 0.18rem 0.3rem;
  color: var(--link);
  text-decoration: none;
  border-radius: 3px;
  transition: background 0.15s;
}

#toc a:hover { background: var(--toc-border); }
#toc a.active { background: var(--toc-border); color: var(--text); font-weight: 600; }

#toc::-webkit-scrollbar { width: 5px; }
#toc::-webkit-scrollbar-track { background: var(--toc-bg); }
#toc::-webkit-scrollbar-thumb { background: var(--toc-border); border-radius: 2px; }

.section-heading .permalink {
  opacity: 0.5;
  text-decoration: none;
  font-size: 1em;
  color: var(--muted);
  margin-left: 0.5em;
  font-weight: 400;
  letter-spacing: 0;
  transition: opacity 0.15s;
  padding: 0 0.2em;
}
.section-heading .permalink:hover { opacity: 1; }

#copy-pill {
  position: fixed;
  bottom: 1.5rem;
  transform: translateX(-50%);
  background: var(--accent);
  color: var(--bg);
  font-family: system-ui, sans-serif;
  font-size: 0.75rem;
  padding: 0.35rem 0.9rem;
  border-radius: 999px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 2000;
  white-space: nowrap;
}
#copy-pill.show { opacity: 1; }

/* Indent levels */
.toc-h1 { font-weight: 600; margin-top: 0.6rem; font-size: 0.78rem; }
.toc-h2 { padding-left: 0.8rem !important; font-style: italic; }
.toc-h3 { padding-left: 1.6rem !important; font-size: 0.72rem; color: var(--muted); }
.toc-h3 a { color: var(--muted); }
.toc-h3 a:hover { color: var(--text); }

/* ── Main content ── */
#content {
  flex: 1;
  max-width: 72ch;
  margin: 0 auto;
  padding: 3rem 2rem 6rem;
}

/* ── Typography ── */
h1.section-heading {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--heading-color);
  margin: 3.5rem 0 1.5rem;
  padding-bottom: 0.4rem;
  border-bottom: 2px solid var(--toc-border);
}

h2.section-heading {
  font-size: 1.3rem;
  font-weight: 600;
  font-style: italic;
  color: var(--heading-color);
  margin: 3rem 0 1.2rem;
}

h3.section-heading {
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--heading-color);
  margin: 2.5rem 0 0.8rem;
}

span.discussion-links {
  display: none;
}
[data-discussion="true"] span.discussion-links {
  display: inline;
  font-size: 0.7rem;
  font-weight: 400;
  letter-spacing: 0;
  text-transform: none;
  margin-left: 0.6em;
  opacity: 0.45;
  vertical-align: middle;
}
[data-discussion="true"] span.discussion-links:hover { opacity: 1; }
a.discussion-link { text-decoration: none; color: var(--link); }
a.discussion-link:hover { text-decoration: underline; }
#discussion-toggle {
  display: block;
  width: 100%;
  margin-bottom: 1rem;
  padding: 0.3rem 0.5rem;
  background: none;
  border: 1px solid var(--toc-border);
  border-radius: 4px;
  color: var(--muted);
  font-family: system-ui, sans-serif;
  font-size: 0.72rem;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.15s, color 0.15s;
}
#discussion-toggle:hover { border-color: var(--link); color: var(--text); }
#discussion-toggle.active { border-color: var(--link); color: var(--text); }

p {
  margin-bottom: 1rem;
  text-align: justify;
  hyphens: auto;
}

/* ── In-page asterisk footnotes ── */
.inline-footnote {
  margin: 0.4rem 0 1rem 0;
  padding: 0.4rem 0.8rem;
  border-left: 2px solid var(--toc-border);
  color: var(--muted);
  font-size: 0.82rem;
  line-height: 1.6;
}
.inline-footnote p {
  margin-bottom: 0.3rem;
  text-align: left;
  hyphens: auto;
}
.inline-footnote p:first-child::before {
  content: "* ";
  font-weight: 700;
}
.inline-footnote p:last-child { margin-bottom: 0; }


/* ── Title block ── */
#title-block {
  text-align: center;
  margin: 2rem 0 4rem;
  padding: 2rem 0;
  border-bottom: 1px solid var(--toc-border);
}
#title-block p { text-align: center; }
#title-block h1 {
  font-size: 2.4rem;
  color: var(--heading-color);
  font-weight: 700;
  margin-bottom: 0.5rem;
}
#title-block .author {
  font-size: 1.1rem;
  font-style: italic;
  margin-bottom: 0.4rem;
}
#title-block .meta {
  font-size: 0.85rem;
  color: var(--muted);
  font-family: system-ui, sans-serif;
}

/* ── GitHub source link ── */
#source-link {
  display: block;
  margin-top: 2rem;
  font-size: 0.68rem;
  color: var(--muted);
  text-decoration: none;
  font-family: system-ui, sans-serif;
}
#source-link:hover { color: var(--text); }
#author-link, #forum-link {
  margin-top: 0.2rem;
  font-size: 0.68rem;
  font-family: system-ui, sans-serif;
}

/* ── Inline endnotes ── */
sup.endref {
  cursor: pointer;
  color: var(--link);
  font-size: 0.65em;
}
sup.endref:hover { text-decoration: underline; }
#endnote-popover {
  position: fixed;
  display: none;
  max-width: 320px;
  padding: 0.6rem 0.8rem;
  background: var(--toc-bg);
  border: 1px solid var(--toc-border);
  border-radius: 4px;
  font-size: 0.78rem;
  font-family: system-ui, sans-serif;
  line-height: 1.5;
  color: var(--text);
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  pointer-events: none;
}

/* ── Mobile ── */
#toc-toggle {
  display: none;
}

@media (max-width: 860px) {
  body { flex-direction: column; }

  #mobile-nav {
    position: sticky;
    top: 0;
    z-index: 100;
  }

  #toc-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 0.75rem 1rem;
    background: var(--toc-bg);
    border: none;
    border-bottom: 1px solid var(--toc-border);
    color: var(--text);
    font-family: system-ui, sans-serif;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
  }

  #toc-toggle .arrow {
    font-size: 0.7rem;
    transition: transform 0.2s;
  }

  #toc-toggle[aria-expanded="true"] .arrow {
    transform: rotate(180deg);
  }

  #toc {
    position: static;
    height: auto;
    width: 100%;
    max-height: 0;
    overflow: hidden;
    border-right: none;
    border-bottom: none;
    padding: 0 1rem;
    transition: max-height 0.3s ease, padding 0.3s ease;
  }

  #toc.open {
    max-height: 60vh;
    overflow-y: auto;
    padding: 1rem;
    border-bottom: 1px solid var(--toc-border);
  }

  #toc h2 { display: none; }

  #content { padding: 1.5rem 1rem 4rem; width: 100%; min-width: 0; font-size: 0.75rem; }
  #content p { text-align: left; }
  #title-block p { text-align: center; }
}
"""

TITLE_BLOCK = """\
<div id="title-block">
  <h1>Negative Dialectics</h1>
  <p class="author">Theodor W. Adorno</p>
  <p class="meta">Suhrkamp Verlag © 1970 Frankfurt am Main<br>
  Translated by Dennis Redmond (2001) for educational, non-commercial purposes</p>
</div>
"""


def typographic(text: str) -> str:
    """Replace straight apostrophes with curly ones in heading text."""
    return text.replace("'", "\u2019")


def build_toc(headings: list[tuple]) -> str:
    """Build the sidebar table of contents from (level, text, anchor) triples."""
    lines = ["<ul>"]
    lines.append('  <li class="toc-h1"><a href="#title-block">Negative Dialectics</a></li>')
    for level, text, anchor in headings:
        cls = f"toc-h{level}"
        label = escape(typographic(text))
        lines.append(
            f'  <li class="{cls}"><a href="#{anchor}">{label}</a></li>'
        )
    lines.append("</ul>")
    return "\n".join(lines)


def _consolidate_footnotes(nodes: list) -> list:
    """Consolidate footnote nodes and reposition them after their anchor paragraphs.

    Rules:
    - 'footnote' nodes (new, starts with *) anchor to the most recent body
      paragraph containing '*' (the inline marker), falling back to the last
      body node if none is found.
    - 'footnote_cont' nodes always join the most recently opened footnote group.
    - Consecutive footnote/footnote_cont nodes (no body node between them) are
      paragraph breaks within the same footnote, merged into a single aside.
    - The complete footnote aside is inserted immediately after the anchor node.
    """
    body_nodes = []    # non-footnote nodes, in order
    groups = []        # {'insert_after': int, 'paras': [str]}
    current = None
    last_was_fn = False

    def _find_anchor() -> int:
        """Return index of the most recent body paragraph containing '*'."""
        for i in range(len(body_nodes) - 1, -1, -1):
            bk, bt, _ = body_nodes[i]
            if bk == "p" and "*" in bt:
                return i
        return len(body_nodes) - 1

    for kind, text, anchor in nodes:
        if kind in ("footnote", "footnote_cont"):
            if kind == "footnote" and not last_was_fn:
                # New footnote group anchored to the paragraph with the * marker
                if current is not None:
                    groups.append(current)
                current = {"insert_after": _find_anchor(), "paras": [text]}
            elif current is not None:
                # Same group: either consecutive footnote paragraphs (blank line
                # within footnote) or a continuation from the next page.
                current["paras"].append(text)
            else:
                # Orphan continuation with no prior group — start a new one
                current = {"insert_after": len(body_nodes) - 1, "paras": [text]}
            last_was_fn = True
        else:
            last_was_fn = False
            body_nodes.append((kind, text, anchor))

    if current is not None:
        groups.append(current)

    # If the anchor paragraph ends mid-sentence (page-break split), defer the
    # footnote to the next cleanly-ending paragraph so it doesn't interrupt a sentence.
    for group in groups:
        i = group["insert_after"]
        while i < len(body_nodes) - 1:
            bk, bt, _ = body_nodes[i]
            if bk == "p" and not ends_cleanly_unicode(bt):
                i += 1
            else:
                break
        group["insert_after"] = i

    # Insert footnote asides into body_nodes from last to first to preserve indices
    result = list(body_nodes)
    for group in sorted(groups, key=lambda g: g["insert_after"], reverse=True):
        pos = group["insert_after"] + 1
        result.insert(pos, ("footnote_block", group["paras"], None))

    return result


def _merge_split_paragraphs(nodes: list) -> list:
    """Merge consecutive p nodes where the first ends mid-sentence (page-break artifact).
    Also merges split paragraphs within footnote_block nodes."""
    result = []
    for node in nodes:
        kind, text, anchor = node
        if kind == "footnote_block":
            merged = []
            for para in text:
                if merged and not ends_cleanly_unicode(merged[-1]):
                    merged[-1] = merged[-1] + " " + para
                else:
                    merged.append(para)
            result.append(("footnote_block", merged, anchor))
        elif (result and result[-1][0] == "p" and kind == "p"
                and not ends_cleanly_unicode(result[-1][1])):
            pk, pt, pa = result.pop()
            result.append(("p", pt + " " + text, pa))
        else:
            result.append(node)
    return result


def build_html(nodes) -> str:
    """Render the parsed node stream to HTML."""
    nodes = _consolidate_footnotes(list(nodes))
    nodes = _merge_split_paragraphs(nodes)

    toc_headings = []  # (level, text, anchor)
    body_parts = []
    used_anchors: dict[str, int] = {}

    # Deduplicate anchors (e.g. two sections named "Introduction")
    def unique_anchor(anchor: str) -> str:
        if anchor not in used_anchors:
            used_anchors[anchor] = 0
            return anchor
        used_anchors[anchor] += 1
        return f"{anchor}-{used_anchors[anchor]}"

    # Track whether we've passed the initial title block
    past_title = False

    for kind, text, anchor in nodes:
        if kind == "page":
            pass
        elif kind == "footnote_block":
            # text is a list of paragraph strings
            ps = "\n".join(f"<p>{escape(p, quote=False)}</p>" for p in text)
            body_parts.append(f'<aside class="inline-footnote">\n{ps}\n</aside>\n')
        elif kind in ("h1", "h2", "h3"):
            past_title = True
            level = int(kind[1])
            uid = unique_anchor(anchor)
            toc_headings.append((level, text, uid))
            posts = DISCUSSION_LINKS.get(uid, [])
            if posts:
                seen: dict[str, int] = {}
                parts = []
                for username, url in posts:
                    seen[username] = seen.get(username, 0) + 1
                counts = {u: 0 for u in seen}
                for username, url in posts:
                    counts[username] += 1
                    label = (
                        f"{username} ({counts[username]})"
                        if seen[username] > 1 else username
                    )
                    parts.append(
                        f'<a href="{url}" class="discussion-link"'
                        f' title="Discussion at TPF" target="_blank"'
                        f' rel="noopener">{label}</a>'
                    )
                disc_html = (
                    ' <span class="discussion-links">'
                    + ' | '.join(parts)
                    + '</span>'
                )
            else:
                disc_html = ""
            permalink = f'<a href="#{uid}" class="permalink" title="Copy link" aria-label="Copy link to this section">§</a>'
            body_parts.append(
                f'\n<h{level} id="{uid}" class="section-heading">'
                f"{escape(typographic(text))}{permalink}{disc_html}</h{level}>\n"
            )
        elif kind == "p":
            if not past_title and len(text) < 80:
                # Still in title/front matter noise — skip very short fragments
                # but don't skip paragraphs that are clearly content
                pass
            # Convert inline asterisk footnote markers to superscripts
            text_html = re.sub(r'\*', '<sup>*</sup>', escape(text, quote=False))
            body_parts.append(f"<p>{text_html}</p>\n")

    toc_html = build_toc(toc_headings)

    section_to_endnote_js = (
        "{\n"
        + "".join(f"    '{k}': '{v}',\n" for k, v in SECTION_TO_ENDNOTE.items())
        + "  }"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Negative Dialectics — Theodor W. Adorno (trans. Dennis Redmond, 2001)</title>
  <meta name="description" content="Negative Dialectics by Theodor W. Adorno, translated by Dennis Redmond (2001). A freely available English translation of Adorno's major philosophical work, with full navigation by section and subsection.">
  <meta property="og:title" content="Negative Dialectics — Theodor W. Adorno">
  <meta property="og:description" content="Adorno's Negative Dialectics in Dennis Redmond's 2001 English translation, with navigation anchors for every section and subsection.">
  <meta property="og:type" content="book">
  <meta property="og:url" content="https://negativedialectics.org">
  <link rel="canonical" href="https://negativedialectics.org">
  <link rel="icon" href="favicon.ico">
  <meta name="author" content="Theodor W. Adorno">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,400;1,400&display=swap" rel="stylesheet">
  <style>
{CSS}
  </style>
{('  <script src="https://hypothes.is/embed.js" async></script>' + chr(10)) if HYPOTHESIS else ""}</head>
<body>

<div id="mobile-nav">
<button id="toc-toggle" aria-expanded="false" aria-controls="toc">
  Contents <span class="arrow">▼</span>
</button>

<nav id="toc" aria-label="Table of contents">
  <h2>Contents</h2>
  <button id="theme-toggle" aria-label="Toggle light/dark mode">☀ Light</button>
  <button id="mono-toggle" aria-label="Toggle monospace font">Aa Monospace</button>
  <button id="discussion-toggle" aria-label="Toggle reading group links" title="Show links to reading group posts at The Philosophy Forum">Show TPF links</button>
{toc_html}
  <a id="source-link" href="https://github.com/jamalrob/adorno-negative-dialectics">Source on GitHub</a>
  <a id="author-link" href="https://blog.alistairrobinson.me/">Built by J. Alistair Robinson</a>
  <a id="forum-link" href="https://www.thephilosophyforum.com">Built for The Philosophy Forum</a>
</nav>
</div>

<main id="content">
{TITLE_BLOCK}
{"".join(body_parts)}
</main>

<script>
(function () {{
  var btn  = document.getElementById('theme-toggle');
  var root = document.documentElement;

  function isDark() {{
    if (root.dataset.theme) return root.dataset.theme === 'dark';
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  }}

  function applyTheme(dark) {{
    root.dataset.theme = dark ? 'dark' : 'light';
    btn.textContent = dark ? '\u2600 Light' : '\u263d Dark';
    try {{ localStorage.setItem('nd-theme', dark ? 'dark' : 'light'); }} catch(e) {{}}
  }}

  try {{
    var savedTheme = localStorage.getItem('nd-theme');
    applyTheme(savedTheme === 'dark');
  }} catch(e) {{ applyTheme(false); }}

  btn.addEventListener('click', function () {{ applyTheme(!isDark()); }});

  // ── Mono toggle ──
  var monoBtn = document.getElementById('mono-toggle');
  function applyMono(mono) {{
    root.dataset.mono = mono ? 'true' : 'false';
    monoBtn.classList.toggle('active', mono);
    try {{ localStorage.setItem('nd-mono', mono ? 'true' : 'false'); }} catch(e) {{}}
  }}
  try {{
    applyMono(localStorage.getItem('nd-mono') === 'true');
  }} catch(e) {{ applyMono(false); }}
  monoBtn.addEventListener('click', function () {{
    applyMono(root.dataset.mono !== 'true');
  }});

  // ── Discussion links toggle ──
  var discBtn = document.getElementById('discussion-toggle');
  function applyDiscussion(on) {{
    root.dataset.discussion = on ? 'true' : 'false';
    discBtn.classList.toggle('active', on);
    try {{ localStorage.setItem('nd-discussion', on ? 'true' : 'false'); }} catch(e) {{}}
  }}
  try {{
    applyDiscussion(localStorage.getItem('nd-discussion') === 'true');
  }} catch(e) {{ applyDiscussion(false); }}
  discBtn.addEventListener('click', function () {{
    applyDiscussion(root.dataset.discussion !== 'true');
  }});

  // ── Mobile TOC toggle ──
  var tocToggle = document.getElementById('toc-toggle');
  var toc = document.getElementById('toc');
  if (tocToggle) {{
    tocToggle.addEventListener('click', function () {{
      var open = toc.classList.toggle('open');
      tocToggle.setAttribute('aria-expanded', open);
    }});
    // Close TOC when a link is tapped
    toc.addEventListener('click', function (e) {{
      if (e.target.tagName === 'A') {{
        toc.classList.remove('open');
        tocToggle.setAttribute('aria-expanded', 'false');
      }}
    }});
  }}
}})();
</script>

<script>
(function () {{
  // Maps body section anchor IDs to endnote section IDs
  var sectionToEndnote = {section_to_endnote_js};

  // Build {{ sectionId: {{ number: text }} }} from the endnotes DOM
  function buildEndnoteMap() {{
    var map = {{}};
    var content = document.getElementById('content');
    var inEndnotes = false, currentSection = null;
    var children = content.children;
    for (var i = 0; i < children.length; i++) {{
      var el = children[i];
      if (el.id === 'endnotes') {{ inEndnotes = true; continue; }}
      if (!inEndnotes) continue;
      if (el.tagName === 'H3' && el.id) {{
        currentSection = el.id;
        map[currentSection] = {{}};
      }} else if (el.tagName === 'P' && currentSection) {{
        var m = el.textContent.match(/^(\\d+)\\.\\s(.+)$/);
        if (m) map[currentSection][m[1]] = m[2].trim();
      }}
    }}
    return map;
  }}

  // Wrap inline endnote refs in body paragraphs
  function processBody(endnoteMap) {{
    var content = document.getElementById('content');
    var children = content.children;
    var h1Section = null, currentSection = null;
    // Matches 1-2 digit number immediately after sentence-ending punctuation,
    // before whitespace or end of string. Avoids &quot; entity boundaries by
    // not including ; in the char class.
    var re = /([.,\u2019\u201d")\\]][a-zA-Z]*|[a-zA-Z])(\\d{{1,2}})(?=[\\s.,;:*]|$)/g;
    for (var i = 0; i < children.length; i++) {{
      var el = children[i];
      if (el.id === 'endnotes') break;
      if (el.tagName === 'H1') {{
        h1Section = sectionToEndnote[el.id] || null;
        currentSection = h1Section;
      }} else if (el.tagName === 'H2') {{
        currentSection = sectionToEndnote[el.id] || h1Section;
      }}
      if (el.tagName !== 'P' || !currentSection) continue;
      var smap = endnoteMap[currentSection];
      if (!smap) continue;
      el.innerHTML = el.innerHTML.replace(re, function (match, punct, num) {{
        var text = smap[num];
        if (!text) return match;
        return punct + '<sup class="endref" data-note="' + text.replace(/"/g, '&quot;') + '">' + num + '</sup>';
      }});
    }}
  }}

  // Floating popover
  var popover = document.createElement('div');
  popover.id = 'endnote-popover';
  document.body.appendChild(popover);

  function showPopover(ref) {{
    popover.textContent = ref.dataset.note;
    popover.style.display = 'block';
    var rect = ref.getBoundingClientRect();
    var ph = popover.offsetHeight, pw = popover.offsetWidth;
    var top = rect.top - ph - 8;
    if (top < 8) top = rect.bottom + 8;
    var left = rect.left + rect.width / 2 - pw / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
    popover.style.top = top + 'px';
    popover.style.left = left + 'px';
  }}

  document.addEventListener('mouseover', function (e) {{
    if (e.target.classList.contains('endref')) showPopover(e.target);
  }});
  document.addEventListener('mouseout', function (e) {{
    if (e.target.classList.contains('endref')) popover.style.display = 'none';
  }});
  document.addEventListener('click', function (e) {{
    if (e.target.classList.contains('endref')) {{
      if (popover.style.display === 'none') showPopover(e.target);
      else popover.style.display = 'none';
      e.stopPropagation();
    }} else {{
      popover.style.display = 'none';
    }}
  }});

  processBody(buildEndnoteMap());
}})();
</script>

<script>
(function () {{
  // ── Section permalink copy ──
  var pill = document.createElement('div');
  pill.id = 'copy-pill';
  pill.textContent = 'Link copied';
  document.body.appendChild(pill);
  var pillTimer;

  document.getElementById('content').addEventListener('click', function (e) {{
    var link = e.target.closest('a.permalink');
    if (!link) return;
    e.preventDefault();
    var url = window.location.origin + window.location.pathname + link.getAttribute('href');
    navigator.clipboard.writeText(url).then(function () {{
      var rect = document.getElementById('content').getBoundingClientRect();
      pill.style.left = (rect.left + rect.width / 2) + 'px';
      clearTimeout(pillTimer);
      pill.classList.add('show');
      pillTimer = setTimeout(function () {{ pill.classList.remove('show'); }}, 1800);
    }});
  }});
}})();
</script>

<script>
(function () {{
  // ── Scroll spy ──
  var tocEl = document.getElementById('toc');
  var headings = Array.from(document.querySelectorAll('#content h1[id], #content h2[id], #content h3[id]'));
  var linkMap = {{}};
  headings.forEach(function (h) {{
    var a = tocEl.querySelector('a[href="#' + h.id + '"]');
    if (a) linkMap[h.id] = a;
  }});
  var activeId = null;

  function scrollTocTo(link) {{
    var top = link.offsetTop;
    var bottom = top + link.offsetHeight;
    var pad = 48;
    if (top < tocEl.scrollTop + pad) {{
      tocEl.scrollTop = top - pad;
    }} else if (bottom > tocEl.scrollTop + tocEl.clientHeight - pad) {{
      tocEl.scrollTop = bottom - tocEl.clientHeight + pad;
    }}
  }}

  function updateActive() {{
    var best = null;
    for (var i = 0; i < headings.length; i++) {{
      if (headings[i].getBoundingClientRect().top <= 120) {{
        best = headings[i].id;
      }} else {{
        break;
      }}
    }}
    if (best === activeId) return;
    if (activeId && linkMap[activeId]) linkMap[activeId].classList.remove('active');
    activeId = best;
    if (activeId && linkMap[activeId]) {{
      linkMap[activeId].classList.add('active');
      scrollTocTo(linkMap[activeId]);
    }}
  }}

  window.addEventListener('scroll', updateActive, {{ passive: true }});
  updateActive();

  // ── Reading position memory ──
  try {{
    var saved = localStorage.getItem('nd-scroll');
    if (saved && !window.location.hash) window.scrollTo(0, parseInt(saved, 10));
  }} catch (e) {{}}

  var saveTimer;
  window.addEventListener('scroll', function () {{
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {{
      try {{ localStorage.setItem('nd-scroll', window.scrollY); }} catch (e) {{}}
    }}, 200);
  }}, {{ passive: true }});
}})();
</script>

</body>
</html>
"""


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Extracting text from PDF…")
    result = subprocess.run(
        ["pdftotext", "-layout", str(PDF_PATH), "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed:\n{result.stderr}")

    raw = result.stdout
    print(f"  {len(raw):,} characters, {raw.count(chr(12))} page breaks")

    print("Preprocessing footnotes…")
    raw = preprocess_footnotes(raw)

    print("Parsing document structure…")
    nodes = list(parse(raw))

    headings = [(k, t, a) for k, t, a in nodes if k in ("h1", "h2", "h3")]
    pages = [t for k, t, a in nodes if k == "page"]
    paras = [t for k, t, a in nodes if k == "p"]
    footnotes = [t for k, t, a in nodes if k == "footnote"]
    print(
        f"  {len(headings)} headings "
        f"({sum(1 for k,_,_ in headings if k=='h1')} h1 / "
        f"{sum(1 for k,_,_ in headings if k=='h2')} h2 / "
        f"{sum(1 for k,_,_ in headings if k=='h3')} h3)"
    )
    print(f"  {len(pages)} page markers, {len(paras)} paragraphs, {len(footnotes)} footnote paragraphs")

    print("Rendering HTML…")
    html = build_html(nodes)

    OUT_PATH.write_text(html, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"  Written to {OUT_PATH}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
