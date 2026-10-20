from datetime import datetime

from app.extensions import db


class Job(db.Model):
    # Tên bảng thật trong MySQL
    __tablename__ = "jobs"

    # ==================== KHÓA CHÍNH ====================

    job_id = db.Column(db.Integer, primary_key=True)


    # ==================== KHÓA NGOẠI ====================

    # Job này do Company nào đăng
    company_id = db.Column(
        db.Integer,
        db.ForeignKey("companies.company_id"),
        nullable=False
    )

    # Job này thuộc danh mục công việc nào
    job_category_id = db.Column(
        db.Integer,
        db.ForeignKey("job_categories.job_category_id"),
        nullable=False
    )


    # ==================== THÔNG TIN CÔNG VIỆC ====================

    # Tiêu đề tuyển dụng
    job_title = db.Column(db.String(200), nullable=False)

    # Mô tả công việc
    job_description = db.Column(db.Text, nullable=False)

    # Yêu cầu công việc
    job_requirement = db.Column(db.Text, nullable=False)

    # Kinh nghiệm yêu cầu
    experience = db.Column(db.String(100), nullable=False)

    # Cấp bậc: Intern / Fresher / Junior / Senior...
    level = db.Column(db.String(50), nullable=False)

    # Số lượng cần tuyển
    quantity = db.Column(db.Integer, nullable=False)


    # ==================== HÌNH THỨC LÀM VIỆC ====================

    # ONSITE / REMOTE / HYBRID
    work_mode = db.Column(db.String(20), nullable=False)

    # FULL_TIME / PART_TIME / INTERNSHIP
    job_type = db.Column(db.String(30), nullable=False)


    # ==================== LƯƠNG ====================

    # Có thể NULL nếu công ty để lương thỏa thuận
    min_salary = db.Column(db.Numeric(15, 2), nullable=True)
    max_salary = db.Column(db.Numeric(15, 2), nullable=True)


    # ==================== THÔNG TIN BỔ SUNG ====================

    location = db.Column(db.String(255), nullable=False)

    # Quyền lợi của công việc
    benefit = db.Column(db.Text, nullable=True)

    # Thời gian làm việc, ví dụ: Thứ 2 - Thứ 6
    working_time = db.Column(db.String(255), nullable=True)

    # Hạn cuối nhận hồ sơ
    application_deadline = db.Column(db.Date, nullable=False)


    # ==================== TRẠNG THÁI ====================

    # OPEN / CLOSED / EXPIRED
    job_status = db.Column(
        db.String(20),
        nullable=False,
        default="OPEN"
    )

    # Admin có ẩn tin này hay không
    is_hidden = db.Column(
        db.Boolean,
        nullable=False,
        default=False
    )


    # ==================== THÔNG TIN HỆ THỐNG ====================

    # Thời điểm tạo tin tuyển dụng
    job_created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    # Chuỗi dùng cho URL thân thiện
    # Ví dụ: /jobs/15/java-backend-developer
    job_slug = db.Column(db.String(255), nullable=False)