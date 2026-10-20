from app.services.fuzzy_matcher import fuzzy_match_skill

skills = [
    "Python", "Java", "JavaScript", "React",
    "Docker", "Kubernetes", "PostgreSQL",
    "TypeScript", "Router", "Spring",
    "Flask", "Angular"
]

test_cases = [
    "Pythn",
    "JavScript",
    "Reactt",
    "Dockr",
    "Kubernets",
    "Route",
    "Spring",
    "Angler",
    "Flaskk",
    "Dockerization",
    "Programming",
    "Management",
    "Experience",
    "Developer",
    "Technology"
]

for text in test_cases:
    result = fuzzy_match_skill(text, skills)
    print(f"{text:18} => {result}")