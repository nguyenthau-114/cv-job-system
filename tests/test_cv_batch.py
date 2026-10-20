import csv
import os
import time
from pathlib import Path

from app import create_app
from app.services.cv_service import (
    extract_pdf_text,
    extract_docx_text,
    extract_image_text
)
from app.services.skill_extractor import extract_skills

CV_FOLDER = Path(r"D:\NienLuanNganh\tests\CV")
RESULT_FILE = Path(r"D:\NienLuanNganh\tests\cv_test_results.csv")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}
TEST_LIMIT = 73


def read_cv(file_path):
    """Chọn hàm đọc CV theo định dạng."""
    extension = file_path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf_text(str(file_path))

    if extension == ".docx":
        return extract_docx_text(str(file_path))

    if extension in {".jpg", ".jpeg", ".png"}:
        return extract_image_text(str(file_path))

    return ""


def test_cv(file_path):
    """Đọc CV, nhận diện kỹ năng và thống kê kết quả."""
    start_time = time.perf_counter()

    result = {
        "file_name": file_path.name,
        "file_type": file_path.suffix.lower(),
        "status": "FAILED",
        "text_length": 0,
        "skill_count": 0,
        "skills": "",
        "processing_seconds": 0,
        "error": ""
    }

    try:
        text = read_cv(file_path)
        result["text_length"] = len(text)

        if not text.strip():
            result["status"] = "NO_TEXT"
        else:
            skills = extract_skills(text)
            result["skill_count"] = len(skills)
            result["skills"] = ", ".join(
                skill["skill_name"] for skill in skills
            )
            result["status"] = "SUCCESS"

    except Exception as error:
        result["error"] = str(error)[:200]

    result["processing_seconds"] = round(
        time.perf_counter() - start_time, 2
    )

    return result


def main():
    """Kiểm thử lần lượt các CV và xuất kết quả CSV."""
    if not CV_FOLDER.is_dir():
        print("Không tìm thấy thư mục CV:", CV_FOLDER)
        return

    files = sorted(
        (
            path for path in CV_FOLDER.rglob("*")
            if path.is_file()
            and path.suffix.lower() in ALLOWED_EXTENSIONS
        ),
        key=lambda path: str(path).casefold()
    )

    print("Tổng CV tìm thấy:", len(files))

    if not files:
        return

    # Lần đầu chỉ kiểm thử 10 CV.
    selected_files = files[:TEST_LIMIT]
    results = []

    for index, file_path in enumerate(selected_files, start=1):
        print(f"\n[{index}/{len(selected_files)}] {file_path.name}")

        result = test_cv(file_path)
        results.append(result)

        print("Trạng thái:", result["status"])
        print("Số ký tự:", result["text_length"])
        print("Số kỹ năng:", result["skill_count"])
        print("Kỹ năng:", result["skills"] or "Không có")

        if result["error"]:
            print("Lỗi:", result["error"])

    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with RESULT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    print("\n===== TỔNG KẾT =====")
    print("Đã kiểm thử:", len(results))
    print("Đọc được:", sum(r["status"] == "SUCCESS" for r in results))
    print("Không đọc được chữ:", sum(r["status"] == "NO_TEXT" for r in results))
    print("Gặp lỗi:", sum(r["status"] == "FAILED" for r in results))
    print("Kết quả lưu tại:", RESULT_FILE)


if __name__ == "__main__":
    app = create_app()

    with app.app_context():
        main()