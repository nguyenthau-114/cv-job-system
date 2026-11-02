#Nghiệp vụ tạo, quản lý và cập nhật tin tuyển dụng.
import re
import unicodedata
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from app.extensions import db
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.company import Company
from app.models.skill import Skill
from app.services.skill_extractor import extract_skills

WORK_MODES = {"ONSITE", "REMOTE", "HYBRID"}
JOB_TYPES = {"FULL_TIME", "PART_TIME", "INTERNSHIP"}
LEVELS = {"INTERN", "FRESHER", "JUNIOR", "MIDDLE", "SENIOR", "LEAD"}
WORK_MODE_LABELS = {"ONSITE": "Tại văn phòng", "REMOTE": "Làm việc từ xa", "HYBRID": "Kết hợp"}
JOB_TYPE_LABELS = {"FULL_TIME": "Toàn thời gian", "PART_TIME": "Bán thời gian", "INTERNSHIP": "Thực tập"}


def visible_jobs():
    # Chỉ công khai tin đang tuyển, chưa bị ẩn và còn hạn.
    return Job.query.filter(
        Job.job_status == "OPEN",
        Job.is_hidden.is_(False),
        Job.application_deadline >= date.today()
    )


def load_job_data(jobs):
    """Lấy thông tin công ty và kỹ năng cho cả trang."""
    job_ids = [job.job_id for job in jobs]
    company_ids = {job.company_id for job in jobs}
    companies = {}
    skills_by_job = {job_id: [] for job_id in job_ids}

    if company_ids:
        companies = {
            company.company_id: company
            for company in Company.query.filter(
                Company.company_id.in_(company_ids)
            ).all()
        }

    if job_ids:
        rows = (
            db.session.query(
                JobSkill.job_id,
                JobSkill.requirement_type,
                Skill.skill_name
            )
            .join(Skill, Skill.skill_id == JobSkill.skill_id)
            .filter(JobSkill.job_id.in_(job_ids))
            .order_by(Skill.skill_name.asc())
            .all()
        )
        for job_id, requirement_type, skill_name in rows:
            skills_by_job[job_id].append({
                "name": skill_name,
                "type": requirement_type
            })

    return companies, skills_by_job


def salary_text(job):
    """Hiển thị lương theo triệu VND."""
    minimum = job.min_salary
    maximum = job.max_salary

    def fmt(value):
        return format((value / Decimal("1000000")).normalize(), "f")

    if minimum is not None and maximum is not None:
        return f"{fmt(minimum)} - {fmt(maximum)} triệu"
    if minimum is not None:
        return f"Từ {fmt(minimum)} triệu"
    if maximum is not None:
        return f"Đến {fmt(maximum)} triệu"
    return "Thỏa thuận"


def job_availability(job):
    """Trạng thái để hiển thị tin đã lưu; tin ẩn không được trả nội dung."""
    if job is None or job.is_hidden:
        return "UNAVAILABLE"
    if job.job_status == "CLOSED":
        return "CLOSED"
    if job.job_status == "EXPIRED" or job.application_deadline is None or job.application_deadline < date.today():
        return "EXPIRED"
    return "OPEN" if job.job_status == "OPEN" else "UNAVAILABLE"


def company_website_url(company):
    """Chỉ hiển thị website HTTP(S) có hostname hợp lệ, không kèm thông tin đăng nhập."""
    value = (company.website or "").strip() if company else ""
    try:
        parsed = urlsplit(value)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
                or parsed.password or "\\" in value or any(char.isspace() or ord(char) < 32 for char in value)):
            return None
        parsed.port
        return value
    except ValueError:
        return None


def job_card_data(job, company=None, skills=None, *, job_id=None, saved=False, saved_at=None,
                  application_status=None):
    """Không đưa dữ liệu tin ẩn vào View, kể cả khi Candidate đã từng lưu tin."""
    status = job_availability(job)
    card = {"id": job.job_id if job else job_id, "status": status,
            "is_saved": saved, "saved_at": saved_at}
    if status == "UNAVAILABLE":
        return card
    card.update(
        title=job.job_title, company=company.company_name if company else "Chưa cập nhật công ty",
        logo=company.logo if company else None, salary=salary_text(job), location=job.location,
        experience=job.experience, work_mode=WORK_MODE_LABELS.get(job.work_mode, job.work_mode),
        job_type=JOB_TYPE_LABELS.get(job.job_type, job.job_type), skills=skills or [],
        deadline=job.application_deadline, application_status=application_status,
    )
    return card



def normalize_job_experience(value):
    """Chuẩn hóa đầu vào về giá trị ngắn, không suy diễn đơn vị kinh nghiệm."""
    text = " ".join(unicodedata.normalize("NFC", str(value if value is not None else "")).split())
    number = r"[0-9]+(?:[.,][0-9]+)?"
    amount = rf"{number}(?:\s*[-–—]\s*{number})?"
    # Chỉ rút gọn các mẫu chắc chắn, giữ nguyên ý nghĩa mô tả tự do khác.
    match = re.fullmatch(
        rf"(?:(?P<prefix>dưới|trên|từ|ít nhất|tối thiểu|tối đa)\s+)?"
        rf"(?P<amount>{amount})\s*(?P<unit>năm|tháng)"
        r"(?:\s+kinh nghiệm)*(?P<suffix>\s+trở lên)?",
        text, flags=re.IGNORECASE
    )
    if match:
        prefix = match["prefix"].capitalize() + " " if match["prefix"] else ""
        amount_text = re.sub(r"\s*[-–—]\s*", "–", match["amount"])
        suffix = " trở lên" if match["suffix"] else ""
        text = f"{prefix}{amount_text} {match['unit'].lower()}{suffix}"
    elif re.fullmatch(r"không yêu cầu(?:\s+kinh nghiệm)?", text, flags=re.IGNORECASE):
        text = "Không yêu cầu"

    if not text:
        raise ValueError("Vui lòng nhập kinh nghiệm.")
    if re.fullmatch(amount, text):
        raise ValueError("Vui lòng ghi rõ đơn vị năm hoặc tháng, ví dụ: 1–2 năm.")
    if len(text) > 100:
        raise ValueError("Kinh nghiệm không được vượt quá 100 ký tự.")
    return text


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
    try:
        data["experience"] = normalize_job_experience(data["experience"])
    except ValueError as error:
        errors["experience"] = str(error)
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
        experience=normalize_job_experience(data["experience"]),
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
