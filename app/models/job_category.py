from app.extensions import db


class JobCategory(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "job_categories"

    # Khóa chính của danh mục việc làm
    job_category_id = db.Column(db.Integer, primary_key=True)

    # Tên danh mục không được để trống và không được trùng
    category_name = db.Column(
        db.String(100),
        nullable=False,
        unique=True
    )