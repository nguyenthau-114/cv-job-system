from app import create_app
from app.extensions import db
from app.models.job_category import JobCategory

# Giữ nguyên 8 nhóm cũ để không ảnh hưởng job_category_id đang sử dụng.
# Bổ sung BA/Product vì JD yêu cầu nghiệp vụ khác quản lý dự án.
JOB_CATEGORIES = [
    "Software Engineering",
    "Software Testing",
    "Data Science",
    "IT Infrastructure & Operations",
    "Cybersecurity",
    "UI/UX",
    "IT Project Management",
    "Khác",
    "Business Analysis & Product Management",
]

def main():
    app = create_app()
    with app.app_context():
        try:
            existing = {c.category_name.casefold() for c in JobCategory.query.all()}
            added = 0
            for name in JOB_CATEGORIES:
                if name.casefold() not in existing:
                    db.session.add(JobCategory(category_name=name))
                    existing.add(name.casefold())
                    added += 1
            db.session.commit()
            print(f"Seed job categories OK: {added} added")
        except Exception:
            db.session.rollback()
            raise

if __name__ == "__main__":
    main()
