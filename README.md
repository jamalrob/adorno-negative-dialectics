# Negative Dialectics — navigable HTML edition

A single-page HTML edition of Theodor W. Adorno's *Negative Dialectics*, using
Dennis Redmond's 2001 English translation, with a full table of contents and
anchor links for every section and subsection.

Live at **[negativedialectics.org](https://negativedialectics.org)**

## What it is

The Redmond translation is freely available online for non-commercial,
educational purposes. This project converts the PDF into a clean, readable web
page with:

- Sidebar table of contents with three levels of hierarchy (part / section / subsection)
- Direct anchor links to all 148 headings
- Light and dark themes (respects system preference, toggle in the sidebar)
- Mobile-responsive layout with collapsible TOC
- Bitstream Charter serif font, generous line-height

## Files

| File | Description |
|------|-------------|
| `convert.py` | Extracts text from the PDF and generates the HTML |
| `negative-dialectics.html` | The generated HTML file (committed for convenience) |
| `scripts/deploy.sh` | Rsyncs the HTML to the production server |
| `content/` | Reading group notes and annotations |

## Regenerating the HTML

You need [poppler](https://poppler.freedesktop.org/) (`pdftotext`) and Python 3.

Place the Redmond translation PDF in `assets/` with the filename:

```
adorno-theodor-negative-dialectics-2019-dennis-redmond-translation.pdf
```

Then run:

```bash
python3 convert.py
```

## Credits

- *Negative Dialectics* © 1970 Theodor W. Adorno / Suhrkamp Verlag Frankfurt am Main
- English translation by [Dennis Redmond](mailto:metalslorg@gmail.com) (2001),
  made freely available for educational, non-commercial purposes
- PDF edition prepared by [/u/ProbablyNotDave](https://www.reddit.com/r/CriticalTheory/comments/clhpah/a_while_ago_i_asked_rcriticaltheory_if_youd_be/)
