"""Remplit les chapitres II et III d'un gabarit de mémoire Word à partir de fichiers Markdown.

Le gabarit (par exemple « Template de Mémoire Master2.docx ») est copié ; rien d'autre que les blocs de remplissage des
chapitres II et III n'est modifié (page de garde, dédicace, glossaire, introduction, chapitre I, conclusion générale,
bibliographie restent tels quels). Les titres, la police (Times New Roman 12), le texte justifié à interligne 1,5 et les
sauts de section du gabarit sont conservés.

Pris en charge dans le Markdown : titres ##, ###, #### (styles « Titre 2, 3, 4 » du gabarit, sans la numérotation
automatique qui doublerait les numéros écrits), paragraphes (gras, italique, code), listes à puces et numérotées,
tableaux, images, citations (>), légendes (lignes *Figure… / *Tableau…), formules LaTeX $…$ et $$…$$ converties en
équations Word natives si Microsoft Office est installé.
Le marqueur <!-- CONCLUSION --> sépare le corps du chapitre du texte de sa conclusion.

Usage : python scripts/md_to_template.py GABARIT.docx SORTIE.docx --ch2 a.md b.md --ch3 c.md d.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.image.image import Image as DocxImage
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).parent))
from md_to_docx import INLINE, omml, split_row  # noqa: E402

BODY = Pt(12)
MATH_FAILURES: list[str] = []


def math_element(latex: str):
    latex = latex.replace(r"\arg\max", r"\mathrm{argmax}")
    el = omml(latex)
    if el is None:
        MATH_FAILURES.append(latex[:80])
    return el


# ---------------------------------------------------------------------------- texte en ligne
def typography(text: str) -> str:
    """Typographie française : espaces insécables dans les milliers, avant %, : ; ? ! et dans les guillemets."""
    text = re.sub(r"(?<=\d) (?=\d{3}(?!\d))", " ", text)
    text = re.sub(r" (?=[:;?!%»])", " ", text)
    return re.sub(r"« ", "« ", text)


def add_inline(par, text: str, size=BODY, bold=False, italic=False):
    text = re.sub(r"<(https?://[^>]+)>", lambda m: m.group(1), text)
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("$") and part.endswith("$") and len(part) > 2:
            el = math_element(part[1:-1])
            if el is not None:
                par._p.append(el)
                continue
            run = par.add_run(part[1:-1]); run.italic = True
        elif part.startswith("**") and part.endswith("**") and len(part) > 4:
            add_inline(par, part[2:-2], size, True, italic); continue
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            add_inline(par, part[1:-1], size, bold, True); continue
        elif part.startswith("`"):
            run = par.add_run(part[1:-1]); run.font.name = "Courier New"; run.font.size = Pt(max(size.pt - 2, 7))
            run.bold = bold
            continue
        else:
            run = par.add_run(typography(part))
        run.bold = bold or None
        run.italic = italic or None
        run.font.size = size


# ---------------------------------------------------------------------------- blocs
PORTRAIT_SECT = None            # propriétés de section (portrait) du gabarit, copiées autour des pages paysage


def section_marker(doc, sect):
    """Paragraphe minuscule qui porte un saut de section (la section qui SE TERMINE ici suit les propriétés `sect`)."""
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after, pf.line_spacing = Pt(0), Pt(0), Pt(1)
    p.add_run().font.size = Pt(1)
    p._p.get_or_add_pPr().append(sect)


def landscape_page(doc, path: Path, caption_text: str | None):
    """Une page paysage dédiée à une figure large, que le texte d'une page portrait rendrait illisible."""
    import copy
    section_marker(doc, copy.deepcopy(PORTRAIT_SECT))          # termine la section portrait en cours
    img = DocxImage.from_file(str(path))
    width = Cm(25)
    if width * img.px_height / img.px_width > Cm(15.2):
        width = Cm(15.2) * img.px_width / img.px_height
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment, pf.space_before, pf.space_after, pf.keep_with_next = WD_ALIGN_PARAGRAPH.CENTER, Pt(0), Pt(2), True
    p.add_run().add_picture(str(path), width=int(width))
    if caption_text:
        caption(doc, caption_text)
    land = copy.deepcopy(PORTRAIT_SECT)
    pgsz = land.find(qn("w:pgSz"))
    pgsz.set(qn("w:w"), "16840"); pgsz.set(qn("w:h"), "11910"); pgsz.set(qn("w:orient"), "landscape")
    mar = land.find(qn("w:pgMar"))
    for k, v in {"top": "1000", "bottom": "900", "left": "1000", "right": "1000"}.items():
        mar.set(qn("w:" + k), v)
    section_marker(doc, land)


def body_par(doc, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, line=1.5, before=0, keep_next=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment, pf.space_before, pf.space_after, pf.line_spacing = align, Pt(before), Pt(after), line
    pf.keep_with_next = keep_next or None
    return p


def heading(doc, text: str, level: int):
    p = doc.add_paragraph(style={2: "Heading 2", 3: "Heading 3", 4: "Heading 4"}[level])
    numpr = p._p.get_or_add_pPr().get_or_add_numPr()          # coupe la numérotation automatique du style
    numpr.get_or_add_numId().val = 0
    pf = p.paragraph_format
    pf.left_indent, pf.first_line_indent = Cm(0), Cm(0)
    pf.space_before, pf.space_after, pf.keep_with_next = Pt({2: 18, 3: 14, 4: 10}[level]), Pt(6), True
    pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
    r = p.add_run(re.sub(r"[*`]", "", text))
    r.bold = True
    r.font.size = Pt({2: 15, 3: 14, 4: 12.5}[level])
    if level == 4:
        r.italic = True
    r.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44) if level < 4 else RGBColor(0, 0, 0)
    return p


def list_item(doc, marker: str, text: str, depth: int):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    left = Cm(1.0 + 0.8 * depth)
    pf.left_indent, pf.first_line_indent = left, Cm(-0.6)
    pf.tab_stops.add_tab_stop(left)
    pf.alignment, pf.space_after, pf.line_spacing = WD_ALIGN_PARAGRAPH.JUSTIFY, Pt(3), 1.35
    r = p.add_run(marker + "\t"); r.font.size = BODY
    add_inline(p, text)
    return p


def quote(doc, text: str):
    p = doc.add_paragraph()
    pPr = p._p.get_or_add_pPr()
    bdr = OxmlElement("w:pBdr")
    left = OxmlElement("w:left")
    for k, v in {"val": "single", "sz": "24", "space": "8", "color": "2B6CB0"}.items():
        left.set(qn("w:" + k), v)
    bdr.append(left)
    shd = OxmlElement("w:shd")
    for k, v in {"val": "clear", "color": "auto", "fill": "EEF3FA"}.items():
        shd.set(qn("w:" + k), v)
    pPr.append(bdr)
    pPr.append(shd)
    pf = p.paragraph_format
    pf.left_indent, pf.right_indent = Cm(0.6), Cm(0.3)
    pf.alignment, pf.space_before, pf.space_after, pf.line_spacing = WD_ALIGN_PARAGRAPH.JUSTIFY, Pt(6), Pt(10), 1.3
    add_inline(p, text, size=Pt(11))
    return p


def equation(doc, latex: str):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment, pf.space_before, pf.space_after, pf.keep_with_next = WD_ALIGN_PARAGRAPH.CENTER, Pt(6), Pt(8), None
    el = math_element(latex)
    if el is not None:
        p._p.append(el)
    else:
        r = p.add_run(latex); r.italic = True
    return p


def caption_style(doc, name: str):
    from docx.enum.style import WD_STYLE_TYPE
    try:
        return doc.styles[name]
    except KeyError:
        st = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = doc.styles["Normal"]
        return st


def caption(doc, text: str):
    is_table = text.startswith("Tableau")
    p = doc.add_paragraph(style=caption_style(doc, "Légende tableau" if is_table else "Légende figure"))
    pf = p.paragraph_format
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf.space_before, pf.space_after = Pt(10 if is_table else 2), Pt(4 if is_table else 12)
    pf.keep_with_next = True if is_table else None
    add_inline(p, text, size=Pt(10), bold=is_table, italic=not is_table)
    return p


def picture(doc, path: Path):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment, pf.space_before, pf.space_after, pf.keep_with_next = WD_ALIGN_PARAGRAPH.CENTER, Pt(8), Pt(2), True
    img = DocxImage.from_file(str(path))
    width = Cm(15.5)
    if width * img.px_height / img.px_width > Cm(19):
        width = Cm(19) * img.px_width / img.px_height
    p.add_run().add_picture(str(path), width=int(width))
    return p


def shade(cell, fill: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    for k, v in {"val": "clear", "color": "auto", "fill": fill}.items():
        shd.set(qn("w:" + k), v)
    tcPr.append(shd)


def table(doc, rows: list[list[str]]):
    ncols = len(rows[0])
    size = Pt(10 if ncols <= 3 else 9 if ncols <= 5 else 8 if ncols <= 8 else 7)
    t = doc.add_table(rows=1, cols=ncols)
    tblPr = t._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement("w:" + side)
        for k, v in {"val": "single", "sz": "4", "space": "0", "color": "7F7F7F"}.items():
            b.set(qn("w:" + k), v)
        borders.append(b)
    look = tblPr.find(qn("w:tblLook"))
    (look.addprevious(borders) if look is not None else tblPr.append(borders))
    mar = OxmlElement("w:tblCellMar")                        # marges de cellule étroites : plus de place au texte
    for side in ("left", "right"):
        m = OxmlElement("w:" + side); m.set(qn("w:w"), "70"); m.set(qn("w:type"), "dxa"); mar.append(m)
    (look.addprevious(mar) if look is not None else tblPr.append(mar))
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW"); tblPr.insert(0, tblW)
    tblW.set(qn("w:type"), "dxa"); tblW.set(qn("w:w"), "9390")

    def fill_cell(cell, text, bold=False):
        cell.text = ""
        p = cell.paragraphs[0]
        pf = p.paragraph_format
        pf.space_after, pf.space_before, pf.line_spacing, pf.alignment = Pt(1), Pt(1), 1.0, WD_ALIGN_PARAGRAPH.LEFT
        add_inline(p, text, size=size, bold=bold)

    for i, h in enumerate(rows[0]):
        c = t.rows[0].cells[i]
        fill_cell(c, h, bold=True)
        shade(c, "D9E2F3")
    trPr = t.rows[0]._tr.get_or_add_trPr()
    hdr = OxmlElement("w:tblHeader"); hdr.set(qn("w:val"), "true"); trPr.append(hdr)
    for r in rows[1:]:
        row = t.add_row()
        for i in range(ncols):
            fill_cell(row.cells[i], r[i] if i < len(r) else "")
        cs = OxmlElement("w:cantSplit"); cs.set(qn("w:val"), "true"); row._tr.get_or_add_trPr().append(cs)
    set_column_widths(t, rows)
    sp = doc.add_paragraph()
    sp.paragraph_format.space_after = Pt(6)
    return t


def set_column_widths(t, rows: list[list[str]], total_twips: int = 9390):
    """Largeur de chaque colonne proportionnelle à son contenu (moyenne des textes, mais jamais plus étroite que
    son mot le plus long) ; sinon Word répartit à parts égales et gaspille la place des colonnes courtes."""
    ncols = len(rows[0])
    plain = lambda x: typography(re.sub(r"[*$\{}^]", "", x.replace("`", "")))   # noqa: E731
    weights = []
    for c in range(ncols):
        raw = [r[c] if c < len(r) else "" for r in rows]
        cells = [plain(x) for x in raw]
        mean = sum(len(x) for x in cells) / len(cells)
        longest_word = max(
            (len(w) * (1.45 if "`" in x else 1.15) for x, y in zip(raw, cells) for w in re.split(r"[ 	]", y)), default=3)
        weights.append(max(min(mean, 60), longest_word, 4))
    total = sum(weights)
    widths = [max(int(total_twips * w / total), 520) for w in weights]
    scale = total_twips / sum(widths)
    widths = [int(w * scale) for w in widths]
    t.autofit = False
    tblPr = t._tbl.tblPr
    layout = tblPr.find(qn("w:tblLayout"))
    if layout is None:
        layout = OxmlElement("w:tblLayout")
        look = tblPr.find(qn("w:tblLook"))
        (look.addprevious(layout) if look is not None else tblPr.append(layout))
    layout.set(qn("w:type"), "fixed")
    grid = t._tbl.tblGrid
    for gc, w in zip(grid.findall(qn("w:gridCol")), widths):
        gc.set(qn("w:w"), str(w))
    for row in t.rows:
        for cell, w in zip(row.cells, widths):
            tcPr = cell._tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW"); tcPr.insert(0, tcW)
            tcW.set(qn("w:type"), "dxa"); tcW.set(qn("w:w"), str(w))


# ---------------------------------------------------------------------------- rendu Markdown
def render(doc, md: str, base: Path):
    lines = md.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s or s == "---":
            i += 1; continue
        if s.startswith("$$"):
            buf = s[2:]
            while not buf.rstrip().endswith("$$") and i + 1 < len(lines):
                i += 1; buf += " " + lines[i].strip()
            equation(doc, buf.rstrip()[:-2].strip()); i += 1; continue
        m = re.match(r"^(#{1,4})\s+(.*)", s)
        if m:
            heading(doc, m.group(2), min(max(len(m.group(1)), 2), 4)); i += 1; continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\|[\s:|-]+\|$", lines[i].strip()):
                    rows.append(split_row(lines[i]))
                i += 1
            table(doc, rows); continue
        img = re.match(r"^!\[(\[paysage\])?([^\]]*)\]\(([^)]+)\)", s)
        if img:
            path = (base / img.group(3)).resolve()
            if not path.exists():
                print("IMAGE MANQUANTE :", path)
            elif img.group(1):                                    # figure large : page paysage + sa légende
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                cap = lines[j].strip().strip("*") if j < len(lines) and re.match(r"^\*Figure[^*]*\*$", lines[j].strip()) else None
                landscape_page(doc, path, cap)
                i = j if cap else i
            else:
                picture(doc, path)
            i += 1; continue
        if s.startswith(">"):
            quote(doc, s.lstrip("> ").strip()); i += 1; continue
        if re.match(r"^\*(Figure|Tableau)[^*]*\*$", s):
            caption(doc, s.strip("*")); i += 1; continue
        lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)", line)
        if lm:
            marker = "•" if lm.group(2) in "-*" else lm.group(2)
            list_item(doc, marker, lm.group(3), 1 if len(lm.group(1)) >= 2 else 0); i += 1; continue
        add_inline(body_par(doc), s)
        i += 1


# ---------------------------------------------------------------------------- insertion dans le gabarit
def body_children(doc):
    return list(doc.element.body)


def text_of(el) -> str:
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def find_index(doc, startswith: str, after: int = -1, exact: bool = False) -> int:
    for idx, el in enumerate(body_children(doc)):
        if idx > after and el.tag == qn("w:p"):
            t = text_of(el)
            if (t == startswith) if exact else t.startswith(startswith):
                return idx
    raise SystemExit(f"repère introuvable dans le gabarit : {startswith!r}")


def fill_chapter(doc, title_prefix: str, md_files: list[Path]):
    """Remplace le bloc de remplissage situé entre le titre du chapitre et son paragraphe « Conclusion »."""
    kids = body_children(doc)
    t_idx = find_index(doc, title_prefix)
    c_idx = find_index(doc, "Conclusion", after=t_idx)
    title_el, concl_el = kids[t_idx], kids[c_idx]
    global PORTRAIT_SECT
    import copy
    PORTRAIT_SECT = copy.deepcopy(concl_el.find(".//" + qn("w:sectPr")))
    for el in kids[t_idx + 1:c_idx]:
        doc.element.body.remove(el)

    text = "\n\n".join(Path(f).read_text(encoding="utf-8") for f in md_files)
    main, _, concl = text.partition("<!-- CONCLUSION -->")
    base = Path(md_files[0]).parent

    def render_block(md: str, anchor):
        body = doc.element.body
        last = body[-2]                                   # dernier élément avant sectPr final
        render(doc, md, base)
        new, el = [], last.getnext()
        while el is not None and el.tag != qn("w:sectPr"):
            new.append(el); el = el.getnext()
        for e in new:
            anchor.addnext(e); anchor = e
        return new

    render_block(main, title_el)
    new = render_block(concl, concl_el)
    # le saut de section porté par le paragraphe « Conclusion » passe au dernier paragraphe de la conclusion
    sect = concl_el.find(".//" + qn("w:sectPr"))
    if sect is not None and new:
        sect.getparent().remove(sect)
        last_p = [e for e in new if e.tag == qn("w:p")][-1]
        last_p.get_or_add_pPr().append(sect) if hasattr(last_p, "get_or_add_pPr") else \
            _ppr(last_p).append(sect)


def insert_bibliography(doc, md_file: Path):
    """Insère la liste de références (une par paragraphe, retrait suspendu) sous le titre BIBLIOGRAPHIE du gabarit."""
    kids = body_children(doc)
    idx = next((k for k, el in enumerate(kids) if el.tag == qn("w:p") and "Liste complète" in text_of(el)), None)
    if idx is None:
        print("section BIBLIOGRAPHIE introuvable : références non insérées"); return
    body = doc.element.body
    last = body[-2]
    for line in Path(md_file).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.left_indent, pf.first_line_indent = Cm(1.0), Cm(-1.0)
        pf.alignment, pf.space_after, pf.line_spacing = WD_ALIGN_PARAGRAPH.LEFT, Pt(6), 1.15
        add_inline(p, line.strip(), size=Pt(11))
    new, el = [], last.getnext()
    while el is not None and el.tag != qn("w:sectPr"):
        new.append(el); el = el.getnext()
    anchor = kids[idx]
    for e in new:
        anchor.addnext(e); anchor = e


def _ppr(p_el):
    pPr = p_el.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr"); p_el.insert(0, pPr)
    return pPr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template"); ap.add_argument("output")
    ap.add_argument("--ch2", nargs="+", required=True); ap.add_argument("--ch3", nargs="+", required=True)
    ap.add_argument("--biblio", help="fichier Markdown des références, inséré sous BIBLIOGRAPHIE")
    a = ap.parse_args()
    doc = Document(a.template)
    fill_chapter(doc, "CHAPITRE II", [Path(f) for f in a.ch2])
    fill_chapter(doc, "Chapitre III", [Path(f) for f in a.ch3])
    if a.biblio:
        insert_bibliography(doc, Path(a.biblio))
    doc.save(a.output)
    print(f"écrit : {a.output}")
    if MATH_FAILURES:
        print(f"{len(MATH_FAILURES)} formule(s) laissée(s) en texte :")
        for f in MATH_FAILURES:
            print("  ", f)


if __name__ == "__main__":
    main()
