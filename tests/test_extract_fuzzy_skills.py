from app.services.fuzzy_matcher import extract_fuzzy_skills

skills = [
    "Python", "Java", "JavaScript", "React",
    "Docker", "Kubernetes", "PostgreSQL",
    "TypeScript", "Router", "Spring", "Flask"
]

text = """
PROFILE
I designed a route for delivery vehicles.
I enjoy spring weather.

Technical Skills: Pythn, Reactt, Docker
Frameworks:
Flaskk
Kubernets

Education:
Bachelor of Information Technology
"""

results = extract_fuzzy_skills(text, skills)

print("Kết quả Fuzzy Matching:")
for result in results:
    print(
        f"{result['extracted_name']:15} "
        f"=> {result['matched_skill']:15} "
        f"({result['score']}%)"
    )