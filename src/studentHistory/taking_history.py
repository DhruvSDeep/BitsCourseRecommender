import os

def collect_student_history():
    print("--- BITS Student Profile Setup ---")
    print("Please enter your academic details.\n")
    
    # Collect required profile fields based on recommender specifications
    campus = input("Enter your campus (e.g., Pilani, Goa, Hyderabad, Dubai): ").strip()
    admission_year = input("Enter your admission year (e.g., 2023): ").strip()
    degree = input("Enter your degree or dual degree (e.g., B.E. Computer Science): ").strip()
    current_semester = input("Enter your current semester (e.g., 5): ").strip()
    
    # Accept comma-separated lists for multiple electives
    completed_input = input("Enter completed electives (comma-separated, e.g., CS F214, HSS F312): ")
    completed_electives = [elective.strip() for elective in completed_input.split(",") if elective.strip()]
    
    minor = input("Enter your minor, if applicable (leave blank if none): ").strip()

    # Structure the collected data
    profile_data = [
        "STUDENT ACADEMIC PROFILE",
        "=" * 25,
        f"Campus: {campus}",
        f"Admission Year: {admission_year}",
        f"Degree: {degree}",
        f"Current Semester: {current_semester}",
        f"Minor: {minor if minor else 'None'}",
        "-" * 25,
        f"Completed Electives: {', '.join(completed_electives) if completed_electives else 'None'}"
    ]

    # Write the data to a text file
    output_filename = "dataset/student_history.txt"
    with open(output_filename, "w") as file:
        file.write("\n".join(profile_data))
        
    print(f"\nSuccessfully saved student history to {output_filename}")

if __name__ == "__main__":
    collect_student_history()