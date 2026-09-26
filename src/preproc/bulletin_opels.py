"""
Extract ALL course-listing entries from a two-column PDF (e.g. a BITS
Pilani style handbook) into a single deduplicated plain-text list, using
pdfplumber.

This is a variant of the original "electives only, grouped by degree"
extractor: it keeps every course row it finds (core courses, electives,
labs, everything), ignores which degree/department a course happened to
appear under, and simply deduplicates by course code so each course is
listed once even if it shows up under several different degree programs.

Layout assumptions (based on the sample pages):
  - Each page has two side-by-side columns of course tables.
  - Every table repeats a literal header row like
    "Course No   Course Title   L   P   U" followed by a dashed divider
    line -- these are filtered out entirely, not treated as content.
  - Rows look like:   CODE   Course Title   L   P   U
    e.g. "CE F312   Hydraulics Engineering   3   1   4"
  - Some entries show only 1 or 2 of the L/P/U numbers (design/project
    style courses with only a Units value) -- whatever numbers are
    found are right-aligned onto L/P/U (1 number = U, 2 = P and U, etc).
  - Long course titles can wrap across multiple lines, and the L/P/U
    numbers are not guaranteed to sit on any particular line of the
    wrap -- so an entry is treated as everything between one course
    code and the next, and all number-only tokens found anywhere in
    that span are collected, in order, to fill L/P/U.
  - A continuation line belongs to the current course's title unless
    it's a genuine section heading -- detected as a line that is
    ALL CAPS and has 2+ words (e.g. "DISCIPLINE ELECTIVE COURSES",
    "COMPUTER SCIENCE"). We no longer care *what kind* of heading it
    is (department vs. group) -- we only use it to know where one
    course entry ends.
  - Course codes look like 2-6 letters, optionally followed by a space,
    then "F" and 3 digits, e.g. "CE F231", "BITS F313", "CS F211".

The column split and row grouping are position-based (using pdfplumber's
word coordinates), not just text guesses, so this should be reasonably
robust -- but real PDFs are messy. Skim the printed output before
trusting the full run, and adjust the constants below (ROW_TOLERANCE,
the heading heuristic, etc.) if something looks off.
"""

import re

import pdfplumber

# ---------------------------------------------------------------------------
# EDIT THESE LINES, THEN JUST RUN THE FILE (no command-line args needed)
# ---------------------------------------------------------------------------
PDF_PATH = "dataset/bulletin.pdf"      # path to your PDF
FIRST_PAGE = 314                       # first page to extract (1-based)
LAST_PAGE = 333                        # last page to extract (1-based)
OUT_FILE = "dataset/opels.txt"         # name of the text file to write
# ---------------------------------------------------------------------------

CODE_RE = re.compile(r'^([A-Z]{2,6})\s+(F\d{3}[A-Z]?)\b\s*(.*)$')
ROW_TOLERANCE = 3  # points; words within this many points of 'top' are one row
TABLE_HEADER_WORDS = {"COURSE", "NO", "TITLE", "L", "P", "U"}


def find_column_split(page, search_frac=(0.30, 0.70)):
    """
    Find the x-coordinate of the true gutter between the two columns:
    the widest vertical strip, within the middle band of the page, that
    no word's bounding box overlaps anywhere on the page. Falls back to
    the page midpoint if nothing clear is found.
    """
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
    """
    Grab words whose left edge falls in [x0, x1), group them into visual
    rows by vertical position, and return each row as (top, text).
    """
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
    """
    A genuine section/department heading: fully upper-case with 2+ words.
    (Course titles wrap in title/sentence case, so this reliably tells
    a heading apart from a wrapped title continuation.) We only use this
    to know where a course entry ends -- we don't care any more whether
    it's a "department" or "group" heading.
    """
    return text.isupper() and len(text.split()) >= 2


def extract_numeric_tokens(text):
    """Pull out standalone digit-only tokens; return (remaining_text, [numbers])."""
    tokens = text.split()
    nums = [t for t in tokens if t.isdigit()]
    rest = [t for t in tokens if not t.isdigit()]
    return ' '.join(rest).strip(), nums


def parse_column(row_texts):
    """
    Turn (top, text) rows from one column into course records. An entry
    spans everything from one course code up to (but not including) the
    next code or heading line, so wrapped titles and numbers landing on
    any line of the wrap are handled the same way.

    Unlike the electives-only version, we don't track department/group
    headings at all -- headings are only used as a signal that the
    current course entry has ended.
    """
    records = []
    pending = None  # {'code': str, 'title_parts': [str], 'numbers': [str]}

    def flush():
        nonlocal pending
        if pending is not None:
            nums = pending['numbers'][-3:]
            padded = [''] * (3 - len(nums)) + nums
            records.append({
                'Code': pending['code'],
                'Title': ' '.join(pending['title_parts']).strip(),
                'L': padded[0], 'P': padded[1], 'U': padded[2],
            })
        pending = None

    for _, raw in row_texts:
        text = raw.strip()
        if not text or is_divider_line(text) or is_table_header_line(text):
            continue

        code_match = CODE_RE.match(text)
        if code_match:
            flush()  # a new entry starts -> close out any pending one
            code = f"{code_match.group(1)} {code_match.group(2)}"
            title_frag, nums = extract_numeric_tokens(code_match.group(3))
            pending = {'code': code, 'title_parts': [title_frag] if title_frag else [], 'numbers': nums}
            continue

        if pending is not None and not is_heading_line(text):
            # continuation of the current (possibly wrapped) title
            title_frag, nums = extract_numeric_tokens(text)
            if title_frag:
                pending['title_parts'].append(title_frag)
            pending['numbers'].extend(nums)
            continue

        # Heading line (or stray text with nothing pending) -- just ends
        # whatever entry was in progress.
        flush()

    flush()
    return records


def extract_pdf(pdf_path, first_page, last_page):
    all_records = []
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

            left_records = parse_column(left_rows)
            right_records = parse_column(right_rows)

            for rec in left_records + right_records:
                rec['Page'] = page_num
                all_records.append(rec)

    return all_records


def dedupe_courses(records):
    """
    Collapse repeated course codes (the same course listed under several
    different degree programs) down to one entry each, in first-seen
    order. If the same code shows up with a different title text, the
    first one wins and a note is printed so you can sanity-check it.
    """
    seen = {}
    order = []
    for r in records:
        code = r['Code']
        if code not in seen:
            seen[code] = r
            order.append(code)
        elif seen[code]['Title'] != r['Title']:
            print(
                f"Note: {code} appears with differing titles -- keeping "
                f"first seen: {seen[code]['Title']!r} vs {r['Title']!r} "
                f"(page {r['Page']})"
            )
    return [seen[code] for code in order]


def format_output(records):
    """Render one line per unique course: code, title, and L/P/U."""
    lines = []
    for c in records:
        lines.append(f"{c['Code']:<12} {c['Title']:<60} {c['L']:>2} {c['P']:>2} {c['U']:>2}")
    return '\n'.join(lines)


if __name__ == '__main__':
    recs = extract_pdf(PDF_PATH, FIRST_PAGE, LAST_PAGE)
    deduped = dedupe_courses(recs)
    deduped.sort(key=lambda r: r['Code'])  # alphabetical by course code

    output = format_output(deduped)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write(output)

    print(f"Extracted {len(recs)} course rows -> {len(deduped)} unique courses. Wrote {OUT_FILE}\n")
    print(output)