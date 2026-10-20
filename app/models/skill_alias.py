from app.extensions import db


class SkillAlias(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "skill_aliases"

    # Khóa chính
    skill_alias_id = db.Column(db.Integer, primary_key=True)

    # FK: alias này thuộc kỹ năng chuẩn nào
    skill_id = db.Column(
        db.Integer,
        db.ForeignKey("skills.skill_id"),
        nullable=False
    )

    # Tên gọi khác của kỹ năng, ví dụ: JS, Javascript
    # Không cho phép một alias trỏ đến nhiều kỹ năng khác nhau
    alias_name = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )