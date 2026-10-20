from app.extensions import db


class CandidateSkill(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "candidate_skills"

    # Khóa chính
    candidate_skill_id = db.Column(db.Integer, primary_key=True)

    # FK: kỹ năng này được phát hiện từ CV nào
    cv_id = db.Column(
        db.Integer,
        db.ForeignKey("cvs.cv_id"),
        nullable=False
    )

    # FK: kỹ năng này tương ứng với Skill chuẩn nào
    skill_id = db.Column(
        db.Integer,
        db.ForeignKey("skills.skill_id"),
        nullable=False
    )

    # Tên kỹ năng đúng như hệ thống phát hiện trong CV
    # Ví dụ CV viết "JS", nhưng skill_id có thể trỏ tới "JavaScript"
    extracted_name = db.Column(db.String(100), nullable=False)
    # Nguồn gốc kỹ năng: hệ thống phát hiện hoặc ứng viên tự bổ sung
    source = db.Column(db.Enum("EXACT", "FUZZY", "MANUAL"), nullable=False, default="EXACT")

    # Một CV không được lưu trùng cùng một Skill chuẩn
    __table_args__ = (
        db.UniqueConstraint(
            "cv_id",
            "skill_id",
            name="uq_candidate_skill_cv_skill"
        ),
    )