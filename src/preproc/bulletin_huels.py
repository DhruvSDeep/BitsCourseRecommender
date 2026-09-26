"""
Extract the "Pool of Humanities courses" (HUELs) table from a two-column
BITS Pilani style handbook PDF, using pdfplumber, as a plain list of
course code + title (L/P/U units are read only so they can be stripped
out -- they are not kept in the output).

Layout assumptions (based on the sample "Pool of Humanities..." page):
  - The table lives inside a normal two-column page, in whichever
    column happens to hold it -- so this reuses the same left/right
    column split as the DEL extractor.
  - Extraction only turns on once a line containing the heading text
    "Pool of Humanities courses" is seen (case-insensitive), so
    anything earlier on the page (e.g. Project Type Courses, or the
    descriptive paragraph right under the heading) is ignored
    automatically rather than being mistaken for course rows.
  - It turns back off as soon as it hits another ALL-CAPS heading line,
    or a line mentioning a different "Pool of ..." table -- whichever
    comes first -- so a following, unrelated pool won't leak in.
  - Rows look like: CODE   Course Title   L   P   U, e.g.
    "BITS F214   Science, Technology and Modernity   3   0   3". A
    title can wrap onto extra lines, with the L/P/U numbers landing on
    any line of the wrap (sometimes the first, sometimes the last).
    Every digit-like token -- including a trailing '*' such as "4*" --
    is stripped out wherever it appears, since only the code + title
    are wanted.
  - Course codes look like 2-6 letters, optionally a space, then "F"
    and 3 digits, e.g. "BITS F214", "GS F211".

As with the DEL script, this is position-based (pdfplumber word
coordinates), not pure text guessing, but real PDFs are messy -- skim
the printed output before trusting it, and narrow/widen
FIRST_PAGE/LAST_PAGE or tweak HEADING_MARKER if something looks off.
"""

import re

import pdfplumber

# ---------------------------------------------------------------------------
# EDIT THESE, THEN JUST RUN THE FILE (no command-line args needed)
# ---------------------------------------------------------------------------
PDF_PATH = "dataset/bulletin.pdf"      # path to your PDF
FIRST_PAGE = 333                       # first page to scan (1-based)
LAST_PAGE = 335                       # last page to scan (1-based)
OUT_FILE = "dataset/huels.txt"         # name of the text file to write
HEADING_MARKER = "pool of humanities"  # case-insensitive substring marking the table's start
# ---------------------------------------------------------------------------

CODE_RE = re.compile(r'^([A-Z]{2,6})\s+(F\d{3}[A-Z]?)\b\s*(.*)$')
ROW_TOLERANCE = 3  # points; words within this many points of 'top' are one row
TABLE_HEADER_WORDS = {"COURSE", "NO", "TITLE", "L", "P", "U"}
NUM_TOKEN_RE = re.compile(r'^\d+\*?$')                          # "3", "0", "4*" ...
PAGE_FOOTER_RE = re.compile(r'^[IVXLCDM]+-\d+$', re.IGNORECASE)  # e.g. "IV-125"


def find_column_split(page, search_frac=(0.30, 0.70)):
    """Same gutter-finding heuristic as the DEL extractor."""
    words = page.extract_words()
    if not words:
        return page.width / 2

    lo, hi = page.width * search_frac[0], page.width * search_frac[1]

    spans = []
    for w in words:
        x0, x1 = w['x0'], w['x1']
        if x1 <= lo or x0 >= hi:
            continue
        spans.append((max(x0, lo), min(x1, hi)))
    if not spans:
        return (lo + hi) / 2

    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    gaps, prev_end = [], lo
    for s, e in merged:
        if s > prev_end:
            gaps.append((s - prev_end, (prev_end + s) / 2))
        prev_end = max(prev_end, e)
    if hi > prev_end:
        gaps.append((hi - prev_end, (prev_end + hi) / 2))

    if not gaps:
        return (lo + hi) / 2
    gaps.sort(reverse=True)
    return gaps[0][1]


def extract_column_rows(page, x0, x1):
    """Same row-grouping heuristic as the DEL extractor."""
    words = page.extract_words()
    col_words = [w for w in words if x0 <= w['x0'] < x1]
    col_words.sort(key=lambda w: (w['top'], w['x0']))

    rows, current, current_top = [], [], None
    for w in col_words:
        if current_top is None or abs(w['top'] - current_top) <= ROW_TOLERANCE:
            current.append(w)
            current_top = w['top'] if current_top is None else current_top
        else:
            rows.append(current)
            current, current_top = [w], w['top']
    if current:
        rows.append(current)

    row_texts = []
    for row in rows:
        row.sort(key=lambda w: w['x0'])
        row_texts.append((row[0]['top'], " ".join(w['text'] for w in row)))
    return row_texts


def is_divider_line(text):
    """A horizontal rule made only of dashes (and spaces)."""
    stripped = text.replace(' ', '')
    return bool(stripped) and set(stripped) <= {'-'}


def is_table_header_line(text):
    """The repeated 'Course No  Course Title  L  P  U' style label row."""
    cleaned = re.sub(r'[^A-Za-z ]', ' ', text).upper()
    tokens = set(cleaned.split())
    return bool(tokens) and tokens <= TABLE_HEADER_WORDS


def is_heading_line(text):
    """ALL-CAPS, 2+ words -- a section heading, not a wrapped title."""
    return text.isupper() and len(text.split()) >= 2


def strip_numeric_tokens(text):
    """Drop standalone digit tokens, including starred units like '4*'."""
    tokens = [t for t in text.split() if not NUM_TOKEN_RE.match(t)]
    return ' '.join(tokens).strip()


def parse_huel_column(row_texts, capturing):
    """
    Walk one column's rows, keeping only course code/title pairs found
    after HEADING_MARKER has been seen, until a new heading (or another
    'Pool of ...' table) switches capturing back off. Returns
    (records, capturing) so the caller can carry the on/off state into
    the next column/page.
    """
    records = []
    pending = None  # {'code': str, 'title_parts': [str]}

    def flush():
        nonlocal pending
        if pending is not None:
            records.append({
                'Code': pending['code'],
                'Title': ' '.join(pending['title_parts']).strip(),
            })
        pending = None

    for _, raw in row_texts:
        text = raw.strip()
        if (not text or is_divider_line(text) or is_table_header_line(text)
                or PAGE_FOOTER_RE.match(text)):
            continue

        if not capturing:
            if HEADING_MARKER in text.lower():
                capturing = True
            continue  # heading line itself, or anything before it, isn't data

        code_match = CODE_RE.match(text)
        if code_match:
            flush()  # a new entry starts -> close out any pending one
            code = f"{code_match.group(1)} {code_match.group(2)}"
            title_frag = strip_numeric_tokens(code_match.group(3))
            pending = {'code': code, 'title_parts': [title_frag] if title_frag else []}
            continue

        if is_heading_line(text) or 'pool of' in text.lower():
            # a new section, or a different Pool-of-... table, has begun
            flush()
            capturing = False
            continue

        if pending is not None:
            # continuation of the current (possibly wrapped) title
            title_frag = strip_numeric_tokens(text)
            if title_frag:
                pending['title_parts'].append(title_frag)
            continue

        # stray text before the table starts (e.g. the descriptive
        # paragraph under the heading) -- ignore it, keep waiting
        continue

    flush()
    return records, capturing


def extract_huels(pdf_path, first_page, last_page):
    all_records = []
    capturing = False  # carried across columns/pages in reading order
    with pdfplumber.open(pdf_path) as pdf:
        for page_num in range(first_page, last_page + 1):
            idx = page_num - 1  # treat first_page/last_page as 1-based PDF page numbers
            if not (0 <= idx < len(pdf.pages)):
                print(f"Skipping page {page_num}: out of range (PDF has {len(pdf.pages)} pages)")
                continue

            page = pdf.pages[idx]
            split_x = find_column_split(page)

            left_rows = extract_column_rows(page, 0, split_x)
            right_rows = extract_column_rows(page, split_x, page.width)

            left_records, capturing = parse_huel_column(left_rows, capturing)
            right_records, capturing = parse_huel_column(right_rows, capturing)

            all_records.extend(left_records + right_records)

    return all_records


def format_output(records):
    """Render as a simple two-column plain-text list: Code   Title."""
    return '\n'.join(f"{r['Code']:<12} {r['Title']}" for r in records)


if __name__ == '__main__':
    recs = extract_huels(PDF_PATH, FIRST_PAGE, LAST_PAGE)
    output = format_output(recs)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(output + '\n')

    print(f"Extracted {len(recs)} humanities elective courses. Wrote {OUT_FILE}\n")
    print(output)