
import csv
import time
from pathlib import Path

from app import create_app
from app.services.skill_extractor import extract_skills
from app.services.fuzzy_matcher import extract_fuzzy_skills_db, get_fuzzy_context
from tests.test_cv_batch import read_cv, CV_FOLDER, ALLOWED_EXTENSIONS

RESULT_FILE = CV_FOLDER.parent / "fuzzy_cv_results.csv"
TEST_LIMIT = 73


def test_fuzzy_cv(file_path):
    """So sánh kỹ năng Exact + Alias với gợi ý Fuzzy."""
    start_time = time.perf_counter()
    result = {
        "file_name": file_path.name,
        "status": "FAILED",
        "exact_count": 0,
        "exact_skills": "",
        "fuzzy_count": 0,
        "fuzzy_suggestions": "",
        "processing_seconds": 0,
        "error": "",
        "fuzzy_contexts": ""
    }

    try:
        text = read_cv(file_path)

        if not text or not text.strip():
            result["status"] = "NO_TEXT"
        else:
            exact_skills = extract_skills(text)
            fuzzy_skills = extract_fuzzy_skills_db(text, exact_skills)

            result["exact_count"] = len(exact_skills)
            result["exact_skills"] = ", ".join(
                skill["skill_name"] for skill in exact_skills
            )
            result["fuzzy_count"] = len(fuzzy_skills)
            result["fuzzy_contexts"] = " || ".join(
                f'{skill["extracted_name"]}: '
                f'{get_fuzzy_context(text, skill["extracted_name"])}'
                for skill in fuzzy_skills
            )
            result["fuzzy_suggestions"] = "; ".join(
                f'{skill["extracted_name"]} => {skill["skill_name"]} '
                f'({skill["score"]}%, ID={skill["skill_id"]})'
                for skill in fuzzy_skills
            )
            result["status"] = "SUCCESS"
    except Exception as error:
        result["error"] = str(error)[:200]

    result["processing_seconds"] = round(
        time.perf_counter() - start_time, 2
    )
    return result


def main():
    """Kiểm thử CV thật và xuất báo cáo Fuzzy riêng."""
    if not CV_FOLDER.is_dir():
        print("Không tìm thấy thư mục:", CV_FOLDER)
        return

    files = sorted(
        (
            path for path in CV_FOLDER.rglob("*")
            if path.is_file()
            and path.suffix.lower() in ALLOWED_EXTENSIONS
        ),
        key=lambda path: str(path).casefold()
    )[:TEST_LIMIT]

    if not files:
        print("Không tìm thấy CV để kiểm thử.")
        return

    results = []

    for index, file_path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] {file_path.name}")
        result = test_fuzzy_cv(file_path)
        results.append(result)

        print("Trạng thái:", result["status"])
        print("Exact + Alias:", result["exact_count"])
        print("Fuzzy:", result["fuzzy_count"])

        if result["fuzzy_suggestions"]:
            print("Gợi ý:", result["fuzzy_suggestions"])

        if result["error"]:
            print("Lỗi:", result["error"])

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with RESULT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    successful = [r for r in results if r["status"] == "SUCCESS"]

    print("\n===== TỔNG KẾT =====")
    print("Tổng CV:", len(results))
    print("Đọc thành công:", len(successful))
    print("Tổng kỹ năng Exact + Alias:", sum(r["exact_count"] for r in successful))
    print("Tổng gợi ý Fuzzy:", sum(r["fuzzy_count"] for r in successful))
    print("CV có gợi ý Fuzzy:", sum(r["fuzzy_count"] > 0 for r in successful))
    print("Kết quả:", RESULT_FILE)


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main()
