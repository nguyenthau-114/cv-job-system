from app.services.fuzzy_matcher import extract_fuzzy_skills

skills = [
    "Python", "Java", "JavaScript", "React",
    "Docker", "Kubernetes", "PostgreSQL",
    "TypeScript", "Router", "Spring", "Flask"
]

text = """
PROFILE
I designed a route for delivery vehicles.

Technical Skills:
Pythn, Reactt, Docker
Route, Spring, Flaskk
Java, JavaScript

Education:
Bachelor of Information Technology
"""

exact_names = ["Docker", "Spring", "Java", "JavaScript"]

results = extract_fuzzy_skills(text, skills, exact_names)

print("Gợi ý Fuzzy Matching:")
for result in results:
    print(
        f"{result['extracted_name']:15} "
        f"=> {result['matched_skill']:15} "
        f"({result['score']}%)"
    )