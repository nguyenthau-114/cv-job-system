import csv
import re
from pathlib import Path
from app import create_app
from app.services.cv_service import extract_pdf_text, extract_docx_text, extract_image_text
from app.services.skill_extractor import extract_skills, get_skill_pattern

# Đường dẫn thư mục kiểm thử
TEST_DIR = Path(__file__).resolve().parent
CV_DIR = TEST_DIR / "CV"
OUTPUT_FILE = TEST_DIR / "short_skill_context.csv"

TARGET_SKILLS = {"C", "R", "Go", "Technical Support", "Windows"}
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".jpg", ".jpeg", ".png"}

def extract_text(path):
    """Trích xuất văn bản theo định dạng CV."""
    extension = path.suffix.lower()
    if extension == ".pdf":
        return extract_pdf_text(str(path))
    if extension == ".docx":
        return extract_docx_text(str(path))
    return extract_image_text(str(path))

def get_context(text, start, end, window=65):
    """Lấy đoạn văn bản xung quanh vị trí kỹ năng."""
    left = max(0, start - window)
    right = min(len(text), end + window)
    context = text[left:right]
    return re.sub(r"\s+", " ", context).strip()

def main():
    app = create_app()
    results = []

    with app.app_context():
        files = sorted(
            path for path in CV_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        )

        for index, path in enumerate(files, 1):
            print(f"[{index}/{len(files)}] {path.name}")

            try:
                text = extract_text(path)
                detected = extract_skills(text)

                # Chỉ kiểm tra kỹ năng đã được thuật toán nhận diện
                for skill in detected:
                    skill_name = skill["skill_name"]

                    if skill_name not in TARGET_SKILLS:
                        continue

                    extracted_name = skill["extracted_name"]
                    pattern = get_skill_pattern(extracted_name)

                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        results.append({
                            "file_name": path.name,
                            "skill_name": skill_name,
                            "extracted_name": extracted_name,
                            "context": get_context(text, match.start(), match.end())
                        })

            except Exception as error:
                print(f"  Lỗi: {error}")

    with OUTPUT_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["file_name", "skill_name", "extracted_name", "context"]
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nĐã kiểm tra {len(files)} CV.")
    print(f"Tìm thấy {len(results)} ngữ cảnh cần xem xét.")
    print(f"Kết quả: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()