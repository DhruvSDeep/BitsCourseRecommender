"""
recommender.py
==============
Final recommendation layer for the BITS Academic Course Recommender.

Flow:
  1. Load the student profile and all eligible course lists via info_gatherer.
  2. Build a concise context block containing:
       - Student profile summary
       - Relevant DELs (for this student's degree)
       - Full HUEL list
       - Full OPEL list
       - Bulletin unit/course requirements
       - Completed electives (to avoid re-recommending)
  3. Accept a natural-language user query (e.g. "Suggest a DEL related to AI
     with no midsem").
  4. Send everything to Gemini in a single structured prompt and return the
     model's ranked recommendations with justifications.

Public API
----------
  recommend(user_query: str) -> str
      One-shot call: gather info, build prompt, call Gemini, return text.

  recommend_interactive()
      REPL loop: gather info once, then accept queries until the user quits.
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve src/ on sys.path so sibling imports work when called from any cwd
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from info_gatherer import (          # noqa: E402
    gather_student_info,
    get_handout_text,
)
from he_who_calls_ai.ai_info import query_gemini  # noqa: E402


# ===========================================================================
# 1. Build the system prompt  (static rules, role, constraints)
# ===========================================================================

_SYSTEM_PROMPT = """\
You are an expert BITS Pilani academic advisor embedded in a course-recommendation \
system.

YOUR ROLE
---------
Help a BITS student choose elective courses for their upcoming semester based on:
  - Their degree, semester, campus, minor, and completed electives.
  - BITS academic requirements (how many DEL / HUEL units they still need).
  - The courses actually available to them (provided in the context below).
  - Their natural-language preferences / constraints.

HARD RULES  (never violate these)
----------
1. Only recommend courses that appear in the course lists provided to you.
   Do NOT invent course codes or titles.
2. A student cannot take a course they have already completed.
3. A DEL must come from the student's own discipline elective list.
4. A HUEL must come from the HUEL pool.
5. If a preference cannot be verified from the supplied data (e.g. "no midsem"),
   say so explicitly instead of guessing.
6. Keep recommendations concise: course code, title, why it matches the request.

OUTPUT FORMAT
-------------
For each recommended course output:
  • Course Code & Title
  • Category  (DEL / HUEL)
  • Why it matches the student's request
  • Any caveats (e.g. "midsem status not verifiable from handout data")

Then give a brief closing note on remaining requirement coverage.
"""


# ===========================================================================
# 3. Build the user-turn context block
# ===========================================================================

def _build_context(info: dict) -> str:
    """
    Assemble the student profile, program DELs, HUELs, and bulletin
    requirements into a compact LLM-readable context string.
    OPELs are intentionally excluded to keep the prompt within token limits.
    """
    profile = info["profile"]
    del_info = info["del_info"]
    huel_text = info["huel_text"]
    bulletin_rows = info["bulletin"]["rows"]

    # ---- Student profile ----
    completed = (
        ", ".join(profile["completed_electives"])
        if profile["completed_electives"]
        else "None"
    )
    minor_line = f"Minor: {profile['minor']}" if profile["minor"] else "Minor: None"

    profile_block = (
        "=== STUDENT PROFILE ===\n"
        f"Campus          : {profile['campus']}\n"
        f"Admission Year  : {profile['admission_year']}\n"
        f"Degree          : {profile['degree']}\n"
        f"Current Semester: {profile['current_semester']}\n"
        f"{minor_line}\n"
        f"Completed Electives: {completed}\n"
    )

    # ---- Bulletin requirements ----
    req_lines = ["=== BULLETIN REQUIREMENTS (units / courses) ==="]
    for row in bulletin_rows:
        cat = row.get("Category", "").strip()
        units = row.get("Number of Units Required", "").strip()
        courses = row.get("Number of Courses Required", "").strip()
        if cat:
            req_lines.append(f"  {cat}: {units} units, {courses} courses")
    bulletin_block = "\n".join(req_lines)

    # ---- DEL list for this student's programme only ----
    if del_info["matched_heading"]:
        del_block = (
            f"=== DISCIPLINE ELECTIVES (DEL) for {del_info['matched_heading']} ===\n"
            + del_info["del_text"]
        )
    else:
        del_block = (
            "=== DISCIPLINE ELECTIVES (DEL) ===\n"
            "(Could not determine the student's DEL section from their degree input. "
            f"Available sections: {', '.join(del_info['all_headings'])})"
        )

    # ---- HUEL pool ----
    huel_block = "=== HUMANITIES ELECTIVES (HUEL) pool ===\n" + huel_text

    return "\n\n".join([
        profile_block,
        bulletin_block,
        del_block,
        huel_block,
    ])


# ===========================================================================
# 4. Core recommend function
# ===========================================================================

def recommend(user_query: str, info: dict | None = None) -> str:
    """
    Given a natural-language query, return Gemini's course recommendations.

    Parameters
    ----------
    user_query : str
        e.g. "Suggest a DEL related to AI with no midsem",
             "I want an OPEL with no attendance requirement",
             "Find me a HUEL that is project-based"
    info : dict | None
        Pre-loaded info dict from gather_student_info(). If None it is
        fetched automatically (useful when calling recommend() in a loop
        so info is only gathered once).

    Returns
    -------
    str  -- the model's recommendation text
    """
    if info is None:
        print("[recommender] Gathering student info ...")
        info = gather_student_info()

    context = _build_context(info)

    # Final prompt = context + user query
    full_prompt = (
        f"{context}\n\n"
        "=== STUDENT QUERY ===\n"
        f"{user_query.strip()}\n\n"
        "Please recommend the best matching courses from the lists above, "
        "following the hard rules in your instructions."
    )

    print("[recommender] Sending query to Gemini ...")
    response = query_gemini(
        prompt=full_prompt,
        system_prompt=_SYSTEM_PROMPT,
        model="gemini-3.8-flash",
    )
    return response


# ===========================================================================
# 5. Interactive REPL
# ===========================================================================

def recommend_interactive() -> None:
    """
    Gather student info once, then enter a query loop so the user can ask
    multiple questions without re-loading data each time.
    """
    print("\n" + "=" * 65)
    print("  BITS Academic Course Recommender")
    print("=" * 65)
    print("Loading student profile and course data ...")
    info = gather_student_info()

    degree = info["profile"].get("degree", "unknown degree")
    del_heading = info["del_info"].get("matched_heading") or "unknown"
    print(f"\nProfile loaded. Degree: '{degree}'  |  DEL section: '{del_heading}'")
    print("Type your query, or 'quit' / 'exit' to stop.\n")

    while True:
        try:
            query = input("Your query > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not query:
            continue
        if query.lower() in {"quit", "exit", "q"}:
            print("Bye!")
            break

        result = recommend(query, info=info)
        print("\n" + "-" * 65)
        print(result)
        print("-" * 65 + "\n")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    # If a query is passed as a CLI argument, run non-interactively.
    # Otherwise, start the interactive REPL.
    if len(sys.argv) > 1:
        cli_query = " ".join(sys.argv[1:])
        print(recommend(cli_query))
    else:
        recommend_interactive()
