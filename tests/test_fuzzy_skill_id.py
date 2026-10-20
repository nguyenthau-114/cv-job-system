from app import create_app
from app.services.skill_extractor import extract_skills
from app.services.fuzzy_matcher import extract_fuzzy_skills_db

app = create_app()

text = """
Technical Skills:
Pythn, Reactt, Docker, Flaskk, Kubernets
Education:
Bachelor of Information Technology
"""

with app.app_context():
    exact_skills = extract_skills(text)
    fuzzy_skills = extract_fuzzy_skills_db(text, exact_skills)

    print("Kỹ năng Exact + Alias:")
    for skill in exact_skills:
        print(skill)

    print("\nGợi ý Fuzzy:")
    for skill in fuzzy_skills:
        print(skill)