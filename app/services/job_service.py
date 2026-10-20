
import re
import unicodedata
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.services.skill_extractor import extract_skills

WORK_MODES = {"ONSITE", "REMOTE", "HYBRID"}
JOB_TYPES = {"FULL_TIME", "PART_TIME", "INTERNSHIP"}
LEVELS = {"INTERN", "FRESHER", "JUNIOR", "MIDDLE", "SENIOR", "LEAD"}


def validate_job_form(form):
    """Kiểm tra dữ liệu JD trước khi chuyển sang bước xác nhận."""
    fields = [
        "job_title", "job_category_id", "job_description",
        "job_requirement", "experience", "level", "quantity",
        "work_mode", "job_type", "min_salary", "max_salary",
        "location", "benefit", "working_time", "application_deadline"
    ]
    data = {
        field: str(form.get(field, "") or "").strip()
        for field in fields
    }

    errors = {}
    required_fields = {
        "job_title": "Tiêu đề công việc",
        "job_category_id": "Danh mục công việc",
        "job_description": "Mô tả công việc",
        "job_requirement": "Yêu cầu ứng viên",
        "experience": "Kinh nghiệm",
        "level": "Cấp bậc",
        "quantity": "Số lượng tuyển",
        "work_mode": "Hình thức làm việc",
        "job_type": "Loại công việc",
        "location": "Địa điểm",
        "application_deadline": "Hạn ứng tuyển"
    }

    for field, label in required_fields.items():
        if not data[field]:
            errors[field] = f"Vui lòng nhập {label.lower()}."

    if len(data["job_title"]) > 200:
        errors["job_title"] = "Tiêu đề không được vượt quá 200 ký tự."
    if len(data["location"]) > 255:
        errors["location"] = "Địa điểm không được vượt quá 255 ký tự."
    if len(data["experience"]) > 100:
        errors["experience"] = "Kinh nghiệm không được vượt quá 100 ký tự."
    if len(data["working_time"]) > 255:
        errors["working_time"] = "Thời gian làm việc không được vượt quá 255 ký tự."

    if data["level"] and data["level"] not in LEVELS:
        errors["level"] = "Cấp bậc không hợp lệ."
    if data["work_mode"] and data["work_mode"] not in WORK_MODES:
        errors["work_mode"] = "Hình thức làm việc không hợp lệ."
    if data["job_type"] and data["job_type"] not in JOB_TYPES:
        errors["job_type"] = "Loại công việc không hợp lệ."

    try:
        quantity = int(data["quantity"])
        if quantity <= 0:
            raise ValueError
        data["quantity"] = quantity
    except (ValueError, TypeError):
        errors["quantity"] = "Số lượng tuyển phải là số nguyên lớn hơn 0."

    try:
        deadline = date.fromisoformat(data["application_deadline"])
        if deadline < date.today():
            errors["application_deadline"] = "Hạn ứng tuyển không được là ngày đã qua."
    except ValueError:
        errors["application_deadline"] = "Ngày hết hạn không hợp lệ."

    salaries = {}
    for field in ("min_salary", "max_salary"):
        if not data[field]:
            salaries[field] = None
            continue
        try:
            value = Decimal(data[field])
            if not value.is_finite() or value < 0 or value > Decimal("9999999999999.99"):
                raise InvalidOperation
            salaries[field] = value
        except (InvalidOperation, ValueError):
            errors[field] = "Mức lương phải là số hợp lệ không âm."

    if (
        salaries.get("min_salary") is not None
        and salaries.get("max_salary") is not None
        and salaries["min_salary"] > salaries["max_salary"]
    ):
        errors["max_salary"] = "Lương tối đa phải lớn hơn hoặc bằng lương tối thiểu."

    return data, errors


def extract_job_skills(data):
    """Nhận diện kỹ năng từ mô tả và yêu cầu của JD."""
    content = "\n".join([
        data["job_title"],
        data["job_description"],
        data["job_requirement"]
    ])
    return extract_skills(content)


def generate_job_slug(title):
    """Tạo slug từ tiêu đề công việc."""
    text = unicodedata.normalize("NFD", title)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return f"{text[:230].rstrip('-') or 'job'}-{uuid.uuid4().hex[:12]}"


def publish_job(company_id, data, selected_skills):
    """Lưu JD và kỹ năng trong cùng một giao dịch database."""
    job = Job(
        company_id=company_id,
        job_category_id=int(data["job_category_id"]),
        job_title=data["job_title"],
        job_description=data["job_description"],
        job_requirement=data["job_requirement"],
        experience=data["experience"],
        level=data["level"],
        quantity=int(data["quantity"]),
        work_mode=data["work_mode"],
        job_type=data["job_type"],
        min_salary=Decimal(data["min_salary"]) if data["min_salary"] else None,
        max_salary=Decimal(data["max_salary"]) if data["max_salary"] else None,
        location=data["location"],
        benefit=data["benefit"] or None,
        working_time=data["working_time"] or None,
        application_deadline=date.fromisoformat(data["application_deadline"]),
        job_status="OPEN",
        is_hidden=False,
        job_slug=generate_job_slug(data["job_title"])
    )

    try:
        db.session.add(job)
        db.session.flush()

        for skill in selected_skills:
            db.session.add(JobSkill(
                job_id=job.job_id,
                skill_id=skill["skill_id"],
                requirement_type=skill["requirement_type"]
            ))

        db.session.commit()
        return job
    except Exception:
        db.session.rollback()
        raise
