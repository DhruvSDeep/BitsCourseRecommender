"""
info_gatherer.py
================
Reads the student academic profile from dataset/student_history.txt and
retrieves the relevant text chunks needed for course recommendation:

  1. Student profile  -- parsed from student_history.txt
  2. DEL chunk        -- the matching discipline-elective section from dels.txt,
                        resolved via an AI call when the student's degree string
                        is ambiguous or abbreviated (e.g. "cse" -> "COMPUTER SCIENCE")
  3. HUEL list        -- full contents of huels.txt
  4. Bulletin reqs    -- full contents of bulletin_requirements.csv
  5. Handout text     -- full plain-text of a course handout PDF looked up by
                        course code or name from dataset/handouts/

All paths are resolved relative to this file's location so the module works
regardless of the working directory the caller uses.
"""

import csv
import re
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Locate sibling data files robustly
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent          # .../src
_ROOT = _HERE.parent                             # .../postman25-2
_DATASET = _ROOT / "dataset"

STUDENT_HISTORY_PATH = _DATASET / "student_history.txt"
DELS_PATH            = _DATASET / "dels.txt"
HUELS_PATH           = _DATASET / "huels.txt"
OPELS_PATH           = _DATASET / "opels.txt"
BULLETIN_CSV_PATH    = _DATASET / "bulletin_requirements.csv"
HANDOUTS_DIR         = _DATASET / "handouts"

# ---------------------------------------------------------------------------
# Extend sys.path so we can import he_who_calls_ai regardless of how the
# caller runs this script.
# ---------------------------------------------------------------------------
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from he_who_calls_ai.ai_info import query_gemini  # noqa: E402


# ===========================================================================
# 1. Parse student history
# ===========================================================================

def parse_student_history(path: Path = STUDENT_HISTORY_PATH) -> dict:
    """
    Parse the plain-text student profile written by taking_history.py.

    Expected format (example):

        STUDENT ACADEMIC PROFILE
        =========================
        Campus: pila
        Admission Year: 2025
        Degree: cse
        Current Semester: 3
        Minor: None
        -------------------------
        Completed Electives: None

    Returns a dict with keys:
        campus, admission_year, degree, current_semester, minor,
        completed_electives  (list of strings, empty list if 'None')
    """
    profile: dict = {
        "campus": "",
        "admission_year": "",
        "degree": "",
        "current_semester": "",
        "minor": "",
        "completed_electives": [],
    }

    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "campus":
                profile["campus"] = value
            elif key == "admission year":
                profile["admission_year"] = value
            elif key == "degree":
                profile["degree"] = value
            elif key == "current semester":
                profile["current_semester"] = value
            elif key == "minor":
                profile["minor"] = "" if value.lower() == "none" else value
            elif key == "completed electives":
                if value.lower() == "none" or not value:
                    profile["completed_electives"] = []
                else:
                    profile["completed_electives"] = [
                        e.strip() for e in value.split(",") if e.strip()
                    ]

    return profile


# ===========================================================================
# 2. Parse dels.txt into sections
# ===========================================================================

def _parse_dels_sections(path: Path = DELS_PATH) -> dict:
    """
    Split dels.txt into a dict mapping department heading -> raw text block.

    A department heading is an ALL-CAPS line immediately followed by a line
    of '=' characters (as written by the DEL extractor in preproc/).
    """
    text = path.read_text(encoding="utf-8")

    # Match lines that look like "DEPARTMENT NAME\n=====..."
    section_pattern = re.compile(
        r"^([A-Z][A-Z\s\-/&'(),.]+?)\s*\n[=]+",
        re.MULTILINE,
    )

    sections: dict = {}
    matches = list(section_pattern.finditer(text))

    for i, m in enumerate(matches):
        heading = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[heading] = text[start:end].strip()

    return sections


# ===========================================================================
# 3. AI-assisted degree -> section matching
# ===========================================================================

_MATCH_SYSTEM_PROMPT = (
    "You are a BITS Pilani academic assistant. Your only job is to map a student's "
    "degree/programme abbreviation to the EXACT heading that appears in a list of "
    "discipline-elective (DEL) sections.\n\n"
    "Rules:\n"
    "- Reply with ONLY the exact heading string from the list, nothing else.\n"
    "- If no section matches, reply with the single word: NONE\n"
    "- Do not add explanations, punctuation, or extra words."
)


def resolve_degree_to_section(
    degree_input: str,
    section_headings: list,
) -> Optional[str]:
    """
    Use the Gemini model to match `degree_input` (e.g. "cse", "mech engg",
    "B.E. Computer Science") to one of the `section_headings` from dels.txt.

    Returns the matched heading string, or None if no match is found.
    """
    headings_block = "\n".join(f"- {h}" for h in section_headings)
    prompt = (
        f'Student\'s degree/programme input: "{degree_input}"\n\n'
        f"Available DEL section headings:\n{headings_block}\n\n"
        "Which heading best matches the student's degree? "
        "Reply with ONLY that heading or the word NONE."
    )

    response = query_gemini(
        prompt=prompt,
        system_prompt=_MATCH_SYSTEM_PROMPT,
        model="gemini-3.8-flash",
    ).strip()

    if not response or response.upper() == "NONE":
        return None

    # Exact match (case-insensitive)
    response_upper = response.upper()
    for heading in section_headings:
        if heading.upper() == response_upper:
            return heading

    # Fallback: substring containment
    for heading in section_headings:
        if response_upper in heading.upper() or heading.upper() in response_upper:
            return heading

    return None


# ===========================================================================
# 4. Retrieve DEL chunk for the student's degree
# ===========================================================================

def get_del_chunk(degree_input: str, dels_path: Path = DELS_PATH) -> dict:
    """
    Retrieve the DEL text block relevant to `degree_input`.

    Returns a dict:
        {
            "matched_heading": str | None,
            "del_text": str,          # raw text block, empty string if not found
            "all_headings": list[str] # all available section headings
        }
    """
    sections = _parse_dels_sections(dels_path)
    headings = list(sections.keys())

    matched = resolve_degree_to_section(degree_input, headings)

    return {
        "matched_heading": matched,
        "del_text": sections.get(matched, "") if matched else "",
        "all_headings": headings,
    }


# ===========================================================================
# 5. Load HUEL list
# ===========================================================================

def get_huels(path: Path = HUELS_PATH) -> str:
    """Return the full contents of huels.txt as a string."""
    return path.read_text(encoding="utf-8").strip()


# ===========================================================================
# 6. Load bulletin requirements
# ===========================================================================

def get_bulletin_requirements(path: Path = BULLETIN_CSV_PATH) -> dict:
    """
    Parse bulletin_requirements.csv.

    Returns:
        {
            "raw_csv": str,       # raw file text
            "rows": list[dict]    # list of row dicts from csv.DictReader
        }
    """
    raw = path.read_text(encoding="utf-8")
    rows = []
    reader = csv.DictReader(raw.splitlines())
    for row in reader:
        if any(v.strip() for v in row.values()):
            rows.append(dict(row))

    return {
        "raw_csv": raw.strip(),
        "rows": rows,
    }


# ===========================================================================
# 7. Master gather function
# ===========================================================================

def gather_student_info(
    history_path: Path = STUDENT_HISTORY_PATH,
    dels_path: Path = DELS_PATH,
    huels_path: Path = HUELS_PATH,
    bulletin_path: Path = BULLETIN_CSV_PATH,
) -> dict:
    """
    Top-level function: read the student profile and retrieve all relevant
    dataset chunks in one call.

    Returns:
        {
            "profile":   { campus, admission_year, degree, current_semester,
                           minor, completed_electives },
            "del_info":  { matched_heading, del_text, all_headings },
            "huel_text": str,
            "bulletin":  { raw_csv, rows }
        }
    """
    print("[info_gatherer] Parsing student history ...")
    profile = parse_student_history(history_path)
    degree_input = profile.get("degree", "")

    print(f"[info_gatherer] Student degree input: '{degree_input}'")
    print("[info_gatherer] Resolving degree -> DEL section via AI ...")
    del_info = get_del_chunk(degree_input, dels_path)

    if del_info["matched_heading"]:
        print(f"[info_gatherer] Matched DEL section: '{del_info['matched_heading']}'")
    else:
        print(
            "[info_gatherer] WARNING: Could not match degree to a DEL section. "
            f"Available sections: {del_info['all_headings']}"
        )

    print("[info_gatherer] Loading HUEL list ...")
    huel_text = get_huels(huels_path)

    print("[info_gatherer] Loading bulletin requirements ...")
    bulletin = get_bulletin_requirements(bulletin_path)

    return {
        "profile": profile,
        "del_info": del_info,
        "huel_text": huel_text,
        "bulletin": bulletin,
    }


# ===========================================================================
# 8. Handout extraction
# ===========================================================================

# Regex that matches the handout filename pattern: NNN_DEPT_FXXX[A-Z]?.pdf
# The numeric prefix and underscores are stripped; we care about DEPT_FXXX.
_HANDOUT_RE = re.compile(
    r'^\d+_([A-Z]{2,6})_((?:F|G|U|E)\d{3}[A-Z]?)\.pdf$',
    re.IGNORECASE,
)


def _build_handout_index(handouts_dir: Path = HANDOUTS_DIR) -> dict:
    """
    Scan the handouts directory and build a dict that maps a normalised course
    code (e.g. "CS F425") to a list of matching PDF Paths (there can be
    duplicates in the dataset, e.g. two copies of the same handout).

    The normalised key is "<DEPT> <LEVEL+NUMBER>" in upper-case with a single
    space, matching the format used in dels.txt / huels.txt.
    """
    index: dict = {}
    if not handouts_dir.is_dir():
        return index

    for pdf_path in sorted(handouts_dir.iterdir()):
        m = _HANDOUT_RE.match(pdf_path.name)
        if not m:
            continue
        dept = m.group(1).upper()
        number = m.group(2).upper()
        key = f"{dept} {number}"
        index.setdefault(key, []).append(pdf_path)

    return index


# Module-level cache so the directory is only scanned once per process.
_HANDOUT_INDEX: dict = {}


def _get_handout_index() -> dict:
    """Return the cached handout index, building it on first access."""
    global _HANDOUT_INDEX
    if not _HANDOUT_INDEX:
        _HANDOUT_INDEX = _build_handout_index()
    return _HANDOUT_INDEX


def _extract_pdf_text(pdf_path: Path) -> str:
    """Extract and concatenate all page text from a PDF using pdfplumber."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError(
            "pdfplumber is required for handout extraction. "
            "Install it with: pip install pdfplumber"
        ) from exc

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n".join(pages)


def _normalise_code(raw: str) -> str:
    """
    Normalise a raw course code string to the "DEPT FXXX" format used as the
    index key.  Handles variants like:
      - "CS F425"   -> "CS F425"
      - "CSF425"    -> "CS F425"  (no space between dept and code)
      - "cs f425"   -> "CS F425"  (lower-case)
      - "CS_F425"   -> "CS F425"  (underscore separator)
    """
    # Collapse any separator (space / underscore / hyphen) between dept and number
    normalised = re.sub(r'[_\-\s]+', ' ', raw.strip()).upper()
    # If dept and number are run together ("CSF425"), split them
    no_space = re.sub(r'([A-Z]{2,6})((?:F|G|U|E)\d{3}[A-Z]?)', r'\1 \2', normalised)
    return no_space.strip()


def get_handout_text(
    course_identifier: str,
    handouts_dir: Path = HANDOUTS_DIR,
) -> dict:
    """
    Look up and extract the text of a course handout by course code or title.

    The function first tries an exact normalised-code match (e.g. "CS F425").
    If that fails it uses a Gemini AI call to identify the best-matching code
    from the available index keys, enabling fuzzy / natural-language lookup
    such as "Deep Learning" or "artificial intelligence CS".

    Parameters
    ----------
    course_identifier : str
        A course code (e.g. "CS F425", "CS_F425", "csf425") or a course name
        (e.g. "Deep Learning", "Artificial Intelligence").
    handouts_dir : Path
        Directory containing the handout PDFs. Defaults to HANDOUTS_DIR.

    Returns
    -------
    dict with keys:
        matched_code   : str | None   -- the normalised course code that was matched
        pdf_path       : str | None   -- absolute path to the PDF that was used
        alternates     : list[str]    -- other PDF paths for the same code (duplicates)
        handout_text   : str          -- full extracted plain-text, empty if not found
        error          : str | None   -- human-readable error/warning message
    """
    global _HANDOUT_INDEX
    # Rebuild index if the directory changed (or first call)
    if handouts_dir != HANDOUTS_DIR or not _HANDOUT_INDEX:
        _HANDOUT_INDEX = _build_handout_index(handouts_dir)
    index = _HANDOUT_INDEX

    result = {
        "matched_code": None,
        "pdf_path": None,
        "alternates": [],
        "handout_text": "",
        "error": None,
    }

    if not index:
        result["error"] = f"No handout PDFs found in {handouts_dir}"
        return result

    # --- Step 1: try a direct normalised-code lookup ---
    normalised = _normalise_code(course_identifier)
    if normalised in index:
        matched_key = normalised
    else:
        # --- Step 2: AI-assisted fuzzy match ---
        print(
            f"[info_gatherer] '{course_identifier}' not an exact code; "
            "asking AI to match to an available handout ..."
        )
        matched_key = _ai_match_handout_code(course_identifier, list(index.keys()))

    if matched_key is None:
        result["error"] = (
            f"Could not find a handout for '{course_identifier}'. "
            f"Available codes: {sorted(index.keys())[:20]} ..."
        )
        return result

    pdf_paths = index[matched_key]
    chosen_pdf = pdf_paths[0]            # use the first copy
    alternates = [str(p) for p in pdf_paths[1:]]

    print(f"[info_gatherer] Extracting handout text from {chosen_pdf.name} ...")
    try:
        text = _extract_pdf_text(chosen_pdf)
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"PDF extraction failed for {chosen_pdf}: {exc}"
        return result

    result["matched_code"] = matched_key
    result["pdf_path"] = str(chosen_pdf)
    result["alternates"] = alternates
    result["handout_text"] = text
    return result


_HANDOUT_MATCH_SYSTEM_PROMPT = (
    "You are a BITS Pilani academic assistant. Your only job is to match a "
    "student's course description or name to the EXACT course code from a given list.\n\n"
    "Rules:\n"
    "- Reply with ONLY the exact course code string from the list, nothing else.\n"
    "- If no course matches, reply with the single word: NONE\n"
    "- Do not add explanations, punctuation, or extra words."
)


def _ai_match_handout_code(
    identifier: str,
    available_codes: list,
) -> Optional[str]:
    """
    Use Gemini to map a fuzzy course name/identifier to the best code in
    `available_codes`.  Returns the matched code string or None.
    """
    codes_block = "\n".join(f"- {c}" for c in available_codes)
    prompt = (
        f'Course identifier given by student: "{identifier}"\n\n'
        f"Available course codes:\n{codes_block}\n\n"
        "Which course code best matches? Reply with ONLY that code or NONE."
    )

    response = query_gemini(
        prompt=prompt,
        system_prompt=_HANDOUT_MATCH_SYSTEM_PROMPT,
        model="gemini-3.8-flash",
    ).strip()

    if not response or response.upper() == "NONE":
        return None

    response_upper = response.upper()
    # Exact match
    for code in available_codes:
        if code.upper() == response_upper:
            return code
    # Substring fallback
    for code in available_codes:
        if response_upper in code.upper() or code.upper() in response_upper:
            return code

    return None


# ===========================================================================
# Quick smoke-test when run directly
# ===========================================================================

if __name__ == "__main__":
    info = gather_student_info()

    print("\n" + "=" * 60)
    print("STUDENT PROFILE")
    print("=" * 60)
    for k, v in info["profile"].items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print(f"DEL SECTION MATCHED: {info['del_info']['matched_heading']}")
    print("=" * 60)
    del_text = info["del_info"]["del_text"]
    print(del_text[:800] + ("..." if len(del_text) > 800 else ""))

    print("\n" + "=" * 60)
    print("HUEL LIST (first 400 chars)")
    print("=" * 60)
    print(info["huel_text"][:400])

    print("\n" + "=" * 60)
    print("BULLETIN REQUIREMENTS")
    print("=" * 60)
    for row in info["bulletin"]["rows"]:
        print(row)

    # --- Handout extraction demo ---
    print("\n" + "=" * 60)
    print("HANDOUT DEMO: exact code  ->  CS F425 (Deep Learning)")
    print("=" * 60)
    ho1 = get_handout_text("CS F425")
    print(f"  matched_code : {ho1['matched_code']}")
    print(f"  pdf_path     : {ho1['pdf_path']}")
    print(f"  alternates   : {ho1['alternates']}")
    print(f"  error        : {ho1['error']}")
    print("  text preview :", ho1["handout_text"][:300].replace("\n", " "))

    print("\n" + "=" * 60)
    print("HANDOUT DEMO: fuzzy name  ->  'Deep Learning'")
    print("=" * 60)
    ho2 = get_handout_text("Deep Learning")
    print(f"  matched_code : {ho2['matched_code']}")
    print(f"  pdf_path     : {ho2['pdf_path']}")
