from app.services.fuzzy_matcher import extract_skill_phrases

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

Work Experience:
Developed a web application.
"""

phrases = extract_skill_phrases(text)

print("Các cụm được lấy:")
for phrase in phrases:
    print("-", phrase)