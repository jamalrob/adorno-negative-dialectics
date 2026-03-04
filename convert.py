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

# Lines that look like ALL CAPS headings but are actually signatures/attributions
KNOWN_NOT_HEADINGS = {"THEODOR W. ADORNO"}

# ── Utilities ─────────────────────────────────────────────────────────────────


def slugify(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s.strip())
    return re.sub(r"-{2,}", "-", s)


def is_page_number(s: str) -> bool:
    """True for standalone page numbers (arabic or roman, ≤ 5 chars)."""
    return bool(re.match(r"^[ivxlcdm\d]{1,5}$", s, re.IGNORECASE)) and len(s) <= 5


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

    kind ∈ {'h1', 'h2', 'h3', 'p', 'page'}
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
                if leading >= 1:
                    cleaned.append("")   # new paragraph or heading follows
                # else: 0 leading spaces → continuation, no blank needed
            else:
                cleaned.append("")  # end of document, add blank for safety
            i += 1
        else:
            cleaned.append(line)
            i += 1
    lines = cleaned

    lines = merge_split_headings(lines)

    para: list[str] = []

    def flush():
        nonlocal para
        if para:
            yield ("p", " ".join(para), None)
            para = []

    # Suppress everything before the first real h1 heading (title page + TOC)
    preamble = True
    in_endnotes = False
    done = False

    for line in lines:
        if done:
            break
        s = line.strip()

        # ── blanks ──
        if not s:
            yield from flush()
            continue

        # ── skip TOC dot-leader lines and footnote separators ──
        if re.search(r"\.{5,}", s) or re.match(r"^[_\-]{3,}$", s):
            continue


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
  --bg: #1a1814;
  --text: #e8e4dc;
  --muted: #777;
  --accent: #c49a6c;
  --toc-bg: #211f1b;
  --toc-border: #3a3630;
  --page-marker: #555;
  --heading-color: #d4b896;
  --link: #c49a6c;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #1a1814;
    --text: #e8e4dc;
    --muted: #777;
    --accent: #c49a6c;
    --toc-bg: #211f1b;
    --toc-border: #3a3630;
    --page-marker: #555;
    --heading-color: #d4b896;
    --link: #c49a6c;
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

p {
  margin-bottom: 1rem;
  text-align: justify;
  hyphens: auto;
}


/* ── Title block ── */
#title-block {
  text-align: center;
  margin: 2rem 0 4rem;
  padding: 2rem 0;
  border-bottom: 1px solid var(--toc-border);
}
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
#author-link {
  display: block;
  margin-top: 0.4rem;
  padding: 0.18rem 0.3rem;
  font-size: 0.68rem;
  color: var(--muted);
  font-family: system-ui, sans-serif;
}
#author-link a { display: inline; padding: 0; color: var(--muted); text-decoration: none; }
#author-link a:hover { color: var(--text); background: none; }
#forum-link {
  display: block;
  margin-top: 0.4rem;
  padding: 0.18rem 0.3rem;
  font-size: 0.68rem;
  color: var(--muted);
  font-family: system-ui, sans-serif;
}
#forum-link a { display: inline; padding: 0; color: var(--muted); text-decoration: none; }
#forum-link a:hover { color: var(--text); background: none; }

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

  #content { padding: 1.5rem 1rem 4rem; width: 100%; min-width: 0; font-size: 0.85rem; }
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
    for level, text, anchor in headings:
        cls = f"toc-h{level}"
        label = escape(typographic(text))
        lines.append(
            f'  <li class="{cls}"><a href="#{anchor}">{label}</a></li>'
        )
    lines.append("</ul>")
    return "\n".join(lines)


def build_html(nodes) -> str:
    """Render the parsed node stream to HTML."""
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
        elif kind in ("h1", "h2", "h3"):
            past_title = True
            level = int(kind[1])
            uid = unique_anchor(anchor)
            toc_headings.append((level, text, uid))
            body_parts.append(
                f'\n<h{level} id="{uid}" class="section-heading">'
                f"{escape(typographic(text))}</h{level}>\n"
            )
        elif kind == "p":
            if not past_title and len(text) < 80:
                # Still in title/front matter noise — skip very short fragments
                # but don't skip paragraphs that are clearly content
                pass
            body_parts.append(f"<p>{escape(text)}</p>\n")

    toc_html = build_toc(toc_headings)

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
  <meta name="author" content="Theodor W. Adorno">
  <style>
{CSS}
  </style>
</head>
<body>

<div id="mobile-nav">
<button id="toc-toggle" aria-expanded="false" aria-controls="toc">
  Contents <span class="arrow">▼</span>
</button>

<nav id="toc" aria-label="Table of contents">
  <h2>Contents</h2>
  <button id="theme-toggle" aria-label="Toggle light/dark mode">☀ Light</button>
{toc_html}
  <a id="source-link" href="https://github.com/jamalrob/adorno-negative-dialectics">Source on GitHub</a>
  <span id="author-link">Built by: <a href="https://blog.alistairrobinson.me/">J. Alistair Robinson</a></span>
  <span id="forum-link">Built for: <a href="https://www.thephilosophyforum.com">The Philosophy Forum</a></span>
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

    print("Parsing document structure…")
    nodes = list(parse(raw))

    headings = [(k, t, a) for k, t, a in nodes if k in ("h1", "h2", "h3")]
    pages = [t for k, t, a in nodes if k == "page"]
    paras = [t for k, t, a in nodes if k == "p"]
    print(
        f"  {len(headings)} headings "
        f"({sum(1 for k,_,_ in headings if k=='h1')} h1 / "
        f"{sum(1 for k,_,_ in headings if k=='h2')} h2 / "
        f"{sum(1 for k,_,_ in headings if k=='h3')} h3)"
    )
    print(f"  {len(pages)} page markers, {len(paras)} paragraphs")

    print("Rendering HTML…")
    html = build_html(nodes)

    OUT_PATH.write_text(html, encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size // 1024
    print(f"  Written to {OUT_PATH}  ({size_kb} KB)")


if __name__ == "__main__":
    main()
