
from app import create_app
from app.services.fuzzy_matcher import extract_fuzzy_skills_db

TEST_CASES = [
    {
        "name": "01 - Route trong Profile",
        "text": "Profile:\nI planned a Route for delivery vehicles.",
        "expected": []
    },
    {
        "name": "02 - Route trong Technical Skills",
        "text": "Technical Skills:\nRoute, Python, Docker",
        "expected": []
    },
    {
        "name": "03 - Spring trong câu thông thường",
        "text": "Profile:\nI joined a training course last Spring.",
        "expected": []
    },
    {
        "name": "04 - Lỗi chính tả Python",
        "text": "Technical Skills:\nPythn, Docker",
        "expected": ["Python"]
    },
    {
        "name": "05 - Lỗi chính tả React",
        "text": "Technical Skills:\nReactt, Flask",
        "expected": ["React"]
    },
    {
        "name": "06 - Kỹ năng trong Education",
        "text": "Technical Skills:\nDocker\nEducation:\nPythn",
        "expected": []
    },
    {
        "name": "07 - Kỹ năng trong Summary",
        "text": "Technical Skills:\nDocker\nSummary:\nPythn",
        "expected": []
    },
    {
        "name": "08 - Kỹ năng trong Work Experience",
        "text": "Technical Skills:\nDocker\nWork Experience:\nReactt",
        "expected": []
    },
    {
        "name": "09 - Lỗi chính tả Kubernetes",
        "text": "Technical Skills:\nKubernets, Docker",
        "expected": ["Kubernetes"]
    },
    {
        "name": "10 - Kỹ năng trong Projects",
        "text": "Technical Skills:\nDocker\nProjects:\nFlaskk",
        "expected": []
    }
]


def main():
    passed = 0

    for case in TEST_CASES:
        results = extract_fuzzy_skills_db(case["text"])
        actual = sorted(skill["skill_name"] for skill in results)
        expected = sorted(case["expected"])
        success = actual == expected

        if success:
            passed += 1

        print(f'\n{case["name"]}')
        print("Mong đợi:", expected)
        print("Thực tế:", actual)
        print("Kết quả:", "PASS" if success else "FAIL")

    print("\n===== TỔNG KẾT =====")
    print("Tổng test:", len(TEST_CASES))
    print("PASS:", passed)
    print("FAIL:", len(TEST_CASES) - passed)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
