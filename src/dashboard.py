"""
dashboard.py
============
Master CLI dashboard for the BITS Academic Course Recommender.

Run with:
    py -3 src/dashboard.py

Menu structure
--------------
  [1] View profile
  [2] Edit profile
       |- [1] Campus
       |- [2] Admission Year
       |- [3] Degree
       |- [4] Current Semester
       |- [5] Minor
       |- [6] Add completed elective
       |- [7] Remove completed elective
       |- [8] Clear all completed electives
       |- [9] Full reset (re-enter everything)
  [3] Run a recommendation query
  [4] Quit
"""

import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap sys.path so sibling imports work from any working directory
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from info_gatherer import (          # noqa: E402
    STUDENT_HISTORY_PATH,
    parse_student_history,
    gather_student_info,
)
from recommender import recommend    # noqa: E402


# ===========================================================================
# Display helpers
# ===========================================================================

_WIDTH = 62

def _bar(char: str = "=") -> str:
    return char * _WIDTH

def _header(title: str) -> None:
    print()
    print(_bar())
    print(f"  {title}")
    print(_bar())

def _section(title: str) -> None:
    print()
    print(f"  -- {title} --")

def _wrap(text: str, indent: int = 4) -> str:
    prefix = " " * indent
    return textwrap.fill(text, width=_WIDTH - indent,
                         initial_indent=prefix,
                         subsequent_indent=prefix)

def _divider() -> None:
    print(_bar("-"))


# ===========================================================================
# Profile save  (same format as taking_history.py)
# ===========================================================================

def _save_profile(profile: dict) -> None:
    completed = profile.get("completed_electives", [])
    lines = [
        "STUDENT ACADEMIC PROFILE",
        "=" * 25,
        f"Campus: {profile.get('campus', '')}",
        f"Admission Year: {profile.get('admission_year', '')}",
        f"Degree: {profile.get('degree', '')}",
        f"Current Semester: {profile.get('current_semester', '')}",
        f"Minor: {profile.get('minor', '') or 'None'}",
        "-" * 25,
        f"Completed Electives: {', '.join(completed) if completed else 'None'}",
    ]
    STUDENT_HISTORY_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  [saved] {STUDENT_HISTORY_PATH}")


# ===========================================================================
# Profile display
# ===========================================================================

def _show_profile(profile: dict) -> None:
    _header("YOUR ACADEMIC PROFILE")
    fields = [
        ("Campus",           profile.get("campus")           or "(not set)"),
        ("Admission Year",   profile.get("admission_year")   or "(not set)"),
        ("Degree",           profile.get("degree")           or "(not set)"),
        ("Semester",         profile.get("current_semester") or "(not set)"),
        ("Minor",            profile.get("minor")            or "None"),
    ]
    for label, value in fields:
        print(f"  {label:<18}: {value}")

    completed = profile.get("completed_electives", [])
    print(f"  {'Completed Electives':<18}:", end="")
    if not completed:
        print(" None")
    else:
        print()
        for e in completed:
            print(f"    • {e}")


# ===========================================================================
# Profile editor
# ===========================================================================

def _prompt(label: str, current: str) -> str:
    """Prompt for a value; return current if the user presses Enter."""
    display = current if current else "(blank)"
    raw = input(f"  {label} [{display}]: ").strip()
    return raw if raw else current


def _edit_profile_menu(profile: dict) -> dict:
    """Interactive submenu to patch individual profile fields."""
    while True:
        _header("EDIT PROFILE")
        completed = profile.get("completed_electives", [])
        print(f"  [1] Campus           : {profile.get('campus') or '(not set)'}")
        print(f"  [2] Admission Year   : {profile.get('admission_year') or '(not set)'}")
        print(f"  [3] Degree           : {profile.get('degree') or '(not set)'}")
        print(f"  [4] Current Semester : {profile.get('current_semester') or '(not set)'}")
        print(f"  [5] Minor            : {profile.get('minor') or 'None'}")
        print(f"  [6] Add completed elective")
        print(f"  [7] Remove completed elective")
        print(f"  [8] Clear all completed electives")
        print(f"  [9] Full reset (re-enter everything from scratch)")
        print(f"  [0] Back")
        _divider()

        choice = input("  Choice: ").strip()

        if choice == "0":
            break

        elif choice == "1":
            val = _prompt("Campus", profile.get("campus", ""))
            profile["campus"] = val

        elif choice == "2":
            val = _prompt("Admission Year", profile.get("admission_year", ""))
            profile["admission_year"] = val

        elif choice == "3":
            val = _prompt("Degree", profile.get("degree", ""))
            profile["degree"] = val

        elif choice == "4":
            val = _prompt("Current Semester", profile.get("current_semester", ""))
            profile["current_semester"] = val

        elif choice == "5":
            val = _prompt("Minor (leave blank for None)", profile.get("minor", ""))
            profile["minor"] = val

        elif choice == "6":
            code = input("  Elective code to add (e.g. CS F425): ").strip()
            if code and code not in completed:
                completed.append(code)
                profile["completed_electives"] = completed
                print(f"  Added: {code}")
            elif code in completed:
                print(f"  Already in list: {code}")

        elif choice == "7":
            if not completed:
                print("  No completed electives to remove.")
            else:
                print("  Current electives:")
                for i, e in enumerate(completed, 1):
                    print(f"    [{i}] {e}")
                idx = input("  Enter number to remove (or blank to cancel): ").strip()
                if idx.isdigit() and 1 <= int(idx) <= len(completed):
                    removed = completed.pop(int(idx) - 1)
                    profile["completed_electives"] = completed
                    print(f"  Removed: {removed}")

        elif choice == "8":
            confirm = input("  Clear ALL completed electives? [y/N]: ").strip().lower()
            if confirm == "y":
                profile["completed_electives"] = []
                print("  Cleared.")

        elif choice == "9":
            profile = _full_reset()

        else:
            print("  Unknown option.")
            continue

        _save_profile(profile)

    return profile


def _full_reset() -> dict:
    """Collect all fields from scratch, identical to taking_history.py."""
    _header("FULL PROFILE RESET")
    campus          = input("  Campus (e.g. Pilani, Goa, Hyderabad, Dubai): ").strip()
    admission_year  = input("  Admission Year (e.g. 2025): ").strip()
    degree          = input("  Degree (e.g. B.E. Computer Science / cse): ").strip()
    semester        = input("  Current Semester (e.g. 3): ").strip()
    minor           = input("  Minor (leave blank if none): ").strip()
    raw_electives   = input("  Completed Electives (comma-separated, or blank): ")
    completed       = [e.strip() for e in raw_electives.split(",") if e.strip()]

    return {
        "campus": campus,
        "admission_year": admission_year,
        "degree": degree,
        "current_semester": semester,
        "minor": minor,
        "completed_electives": completed,
    }


# ===========================================================================
# Query runner
# ===========================================================================

def _query_loop(info: dict) -> dict:
    """
    Run recommendation queries in a loop.
    Re-uses the same `info` dict so course data is loaded only once.
    Returns the (possibly refreshed) info dict.
    """
    _header("RECOMMENDATION QUERIES")
    print(_wrap(
        "Ask anything — e.g. 'Suggest a DEL related to AI', "
        "'Find a HUEL with no midsem', 'I prefer project-based courses'."
    ))
    print("  Type 'back' to return to the main menu.")
    print("  Type 'refresh' to reload your profile before the next query.")
    print()

    while True:
        _divider()
        try:
            query = input("  Your query > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not query:
            continue
        if query.lower() in {"back", "b", "exit", "quit"}:
            break
        if query.lower() == "refresh":
            print("  Reloading student profile ...")
            info = gather_student_info()
            print("  Done.")
            continue

        print()
        result = recommend(query, info=info)
        if result:
            print()
            # Word-wrap each line of the response for clean terminal display
            for line in result.splitlines():
                if line.strip():
                    print(_wrap(line, indent=2))
                else:
                    print()
        else:
            print("  (No response received — Gemini may be temporarily unavailable.)")

    return info


# ===========================================================================
# Main menu
# ===========================================================================

def main() -> None:
    _header("BITS ACADEMIC COURSE RECOMMENDER")
    print("  CLI Dashboard  |  DEL & HUEL recommendations")
    _divider()

    # Load profile once at startup
    print("  Loading student profile ...")
    profile = parse_student_history()

    # Pre-load full info (course lists) once so queries are fast
    print("  Loading course data (DELs, HUELs, bulletin) ...")
    try:
        info = gather_student_info()
    except Exception as exc:
        print(f"  Warning: could not pre-load course data: {exc}")
        info = None

    while True:
        _header("MAIN MENU")
        print("  [1]  View profile")
        print("  [2]  Edit profile")
        print("  [3]  Run recommendation query")
        print("  [4]  Quit")
        _divider()

        choice = input("  Choice: ").strip()

        if choice == "1":
            profile = parse_student_history()   # always read fresh from disk
            _show_profile(profile)

        elif choice == "2":
            profile = parse_student_history()
            profile = _edit_profile_menu(profile)
            # Reload info after profile change so the next query picks up changes
            print("\n  Reloading course data with updated profile ...")
            try:
                info = gather_student_info()
                print("  Done.")
            except Exception as exc:
                print(f"  Warning: {exc}")

        elif choice == "3":
            if info is None:
                print("\n  Attempting to load course data ...")
                try:
                    info = gather_student_info()
                except Exception as exc:
                    print(f"  Error: {exc}")
                    continue
            info = _query_loop(info)

        elif choice in {"4", "q", "quit", "exit"}:
            print("\n  Goodbye!\n")
            break

        else:
            print("  Unknown option. Please enter 1–4.")


if __name__ == "__main__":
    main()
