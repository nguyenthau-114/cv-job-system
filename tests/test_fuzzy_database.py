from app import create_app
from app.models.skill import Skill
from app.models.skill_alias import SkillAlias
from app.services.fuzzy_matcher import extract_fuzzy_skills

app = create_app()

with app.app_context():
    skills = Skill.query.filter_by(skill_status="ACTIVE").all()
    aliases = SkillAlias.query.all()

    # Tạo danh sách tên chuẩn và alias từ MySQL.
    skill_map = {skill.skill_id: skill.skill_name for skill in skills}
    skill_names = list(skill_map.values())

    for alias in aliases:
        if alias.skill_id in skill_map:
            skill_names.append(alias.alias_name)

    text = """
    PROFILE
    I designed a route for delivery vehicles.

    Technical Skills:
    Pythn, Reactt, Docker
    Flaskk, Kubernets

    Education:
    Bachelor of Information Technology
    """

    exact_names = ["Docker"]

    results = extract_fuzzy_skills(text, skill_names, exact_names)

    print(f"Số kỹ năng đang hoạt động: {len(skills)}")
    print(f"Số alias: {len(aliases)}")
    print("\nGợi ý Fuzzy Matching:")

    for result in results:
        print(
            f"{result['extracted_name']:15} "
            f"=> {result['matched_skill']:20} "
            f"({result['score']}%)"
        )