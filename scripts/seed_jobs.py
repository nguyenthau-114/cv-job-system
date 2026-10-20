
from datetime import date
from decimal import Decimal

from app import create_app
from app.extensions import db
from app.models.company import Company
from app.models.job import Job
from app.models.job_category import JobCategory
from app.models.skill import Skill
from app.models.job_skill import JobSkill
from app.services.job_service import generate_job_slug


# Dữ liệu JD của từng công ty, sẽ bổ sung JD02–JD80 tại đây.
JOBS = [
    {
        "company_name": "VIETTEL SOLUTIONS",
        "job_title": "Business Analyst - Yêu cầu 3 năm kinh nghiệm",
        "category_name": "Business Analysis & Product Management",
        "job_description": (
            "Khảo sát, thu thập và phân tích yêu cầu nghiệp vụ từ khách hàng. "
            "Phân tích quy trình, mô hình hóa nghiệp vụ và xây dựng tài liệu "
            "đặc tả yêu cầu. Phối hợp với khách hàng và đội phát triển để "
            "thống nhất giải pháp, thiết kế chi tiết và nguyên mẫu giao diện. "
            "Quản lý thay đổi yêu cầu, phối hợp nghiệm thu và hỗ trợ "
            "ước lượng khối lượng công việc."
        ),
        "job_requirement": (
            "Tốt nghiệp đại học chuyên ngành phù hợp. "
            "Có ít nhất 3 năm kinh nghiệm phân tích nghiệp vụ. "
            "Có khả năng sử dụng UML, Use Case và BPMN để mô hình hóa "
            "yêu cầu và quy trình nghiệp vụ. Có kinh nghiệm xây dựng "
            "prototype, viết tài liệu và làm việc với khách hàng. "
            "Có kỹ năng giao tiếp, tư duy phản biện, làm việc nhóm "
            "và khả năng sử dụng tiếng Anh trong công việc."
        ),
        "benefit": (
            "Môi trường làm việc chuyên nghiệp tại Viettel; "
            "cơ hội đào tạo và phát triển chuyên môn; "
            "chế độ đãi ngộ, chăm sóc sức khỏe và hoạt động tập thể."
        ),
        "experience": "3 năm",
        "level": "MIDDLE",
        "quantity": 10,
        "work_mode": "ONSITE",
        "job_type": "FULL_TIME",
        "min_salary": Decimal("25000000"),
        "max_salary": Decimal("60000000"),
        "location": "Số 1 Trần Hữu Dực, Mỹ Đình 2, Nam Từ Liêm, Hà Nội",
        "working_time": "Thứ Hai - Thứ Sáu, 08:00 - 17:30",
        "application_deadline": date(2026, 11, 9),
        "skills": {
            "Business Analysis": "REQUIRED",
            "BPMN": "REQUIRED",
            "UML": "REQUIRED",
        },
    },


    {
        "company_name": "VIETTEL SOLUTIONS",
        "job_title": (
            "Kỹ Sư Vận Hành Hệ Thống Công Nghệ Thông Tin - "
            "Tốt Nghiệp ĐHBK; ĐHQG; ĐH Công Nghiệp; "
            "ĐH GTVT; HV CN BCVT"
        ),
        # Chưa gán danh mục khi chưa đối chiếu seed_job_categories.py
        "category_name": "IT Infrastructure & Operations",
        "job_description": (
            "- Giám sát, vận hành các hệ thống CNTT và hạ tầng cung cấp cho khách hàng.\n"
            "- Tiếp nhận, xác minh cảnh báo/sự cố; xử lý bước đầu theo checklist, runbook.\n"
            "- Tạo và cập nhật ticket; phối hợp với các nhóm kỹ thuật chuyên sâu khi sự cố vượt phạm vi xử lý.\n"
            "- Theo dõi quá trình xử lý đến khi dịch vụ được khôi phục; thực hiện bàn giao và báo cáo ca.\n"
            "- Kiểm tra hệ thống khi tiếp nhận vận hành; định kỳ rà soát tình trạng và cảnh báo các rủi ro.\n"
            "- Phối hợp tiếp nhận, kiểm tra các yêu cầu về tài nguyên hệ thống.\n"
            "- Làm việc theo ca luân phiên, có ca đêm, cuối tuần và ngày lễ theo lịch phân công."
        ),
        "job_requirement": (
            "- Tốt nghiệp Đại học loại Khá chuyên ngành CNTT, Điện tử viễn thông hoặc lĩnh vực liên quan. "
            "Tiếng Anh tối thiểu tương đương chứng chỉ TOEIC 550đ trở lên hoặc các chứng chỉ tương đương khác.\n"
            "- Có từ 01 năm kinh nghiệm về Linux, Windows, Network, Database hoặc vận hành hệ thống.\n"
            "- Có kiến thức cơ bản về Linux/Windows Server, TCP/IP, Database và ảo hóa/Cloud.\n"
            "- Có khả năng đọc log, kiểm tra dịch vụ, tài nguyên hệ thống và xử lý sự cố bước đầu.\n"
            "- Ưu tiên có kiến thức về VMware, OpenStack, Docker/Kubernetes, Microservice hoặc công cụ giám sát.\n"
            "- Có trách nhiệm, tuân thủ quy trình và phối hợp tốt trong quá trình xử lý sự cố.\n"
            "- Có thể làm việc tại các địa điểm ở Hà Nội theo phân công."
        ),
        "benefit": (
            "- Mức thu nhập cạnh tranh so với thị trường, phù hợp với phạm vi trách nhiệm công việc và năng lực cá nhân.\n"
            "- Nhận thưởng tiền mặt dịp Lễ, Tết, ngày thành lập Tập đoàn, hỗ trợ ăn trưa, điện thoại, thưởng dự án, nghỉ dưỡng.\n"
            "- Tham gia đầy đủ BHXH, BHYT, BHTN và bảo hiểm sức khỏe riêng của Tập đoàn, khám sức khỏe định kỳ và ưu đãi mua bảo hiểm cho người thân.\n"
            "- Có 12 ngày phép và 15 ngày nghỉ hưởng nguyên lương gồm 11 ngày lễ Tết, 3 ngày nghỉ mát và 1 ngày sáng tạo.\n"
            "- Cơ hội trở thành Quân nhân chuyên nghiệp hoặc Sĩ quan thuộc Bộ Quốc phòng Việt Nam.\n"
            "- Được tham gia các buổi đào tạo nội bộ, được tài trợ kinh phí thi các chứng chỉ quốc tế, tham gia hội thảo chuyên ngành.\n"
            "- Cơ hội luân chuyển và thăng tiến cùng các dự án lớn khác nhau trong hệ sinh thái của Viettel."
        ),
        "experience": "1 năm",
        "level": "JUNIOR",
        "quantity": 10,
        "work_mode": "ONSITE",
        "job_type": "FULL_TIME",
        "min_salary": Decimal("15000000"),
        "max_salary": Decimal("70000000"),
        "location": (
            "Số 1 Trần Hữu Dực, Mỹ Đình 2, Từ Liêm, "
            "Phường Từ Liêm, Hà Nội"
        ),
        "working_time": "Thứ 2 - Thứ 6 (08:00 - 17:30)",
        "application_deadline": date(2026, 11, 12),
        "skills": {
            "Windows Server": "REQUIRED",
            "Microservices": "PREFERRED",
            "Kubernetes": "PREFERRED",
            "Windows": "REQUIRED",
            "Docker": "PREFERRED",
            "VMware": "PREFERRED",
            "TCP/IP": "REQUIRED",
            "Linux": "REQUIRED",
        },
    },


    {
        "company_name": "VIETTEL SOLUTIONS",
        # Tên tạm theo thông tin đã gửi, chờ xác nhận tiêu đề chính thức.
        "job_title": "Fresher System Engineer",
        "category_name": "IT Infrastructure & Operations",
        "job_description": (
            "- Quản trị, vận hành các hệ thống CNTT gồm máy chủ, tủ đĩa, "
            "SAN switch, tape, hệ điều hành và các hệ thống OpenStack/VMware.\n"
            "- Phối hợp vận hành, xử lý sự cố và tối ưu hiệu năng hệ thống, "
            "đảm bảo hoạt động ổn định, an toàn và đúng thiết kế.\n"
            "- Quy hoạch, thiết kế và triển khai hạ tầng CNTT: Cloud, Network, "
            "Storage, Backup, Disaster Recovery (DR), High Availability (HA).\n"
            "- Xây dựng, chuẩn hóa tài liệu kiến trúc hệ thống, quy trình "
            "vận hành (SOP) và tài liệu hướng dẫn vận hành khai thác.\n"
            "- Nghiên cứu, ứng dụng các giải pháp tự động hóa quản lý, "
            "giám sát và xử lý thiết bị phần cứng, hệ điều hành."
        ),
        "job_requirement": (
            "- Tốt nghiệp Đại học chuyên ngành ĐTVT, CNTT loại Khá trở lên "
            "(Fresher/Intern ưu tiên bằng Giỏi).\n"
            "- Am hiểu Linux, có kiến thức về thiết bị phần cứng như "
            "máy chủ và tủ đĩa.\n"
            "- TOEIC tối thiểu 550 điểm hoặc chứng chỉ tương đương.\n"
            "Ưu tiên:\n"
            "- Kinh nghiệm quản trị, thiết kế, triển khai máy chủ, "
            "tủ đĩa, switch, SAN switch và tape.\n"
            "- Kinh nghiệm với hệ thống ảo hóa VMware, OpenStack.\n"
            "- Kinh nghiệm Tuning & Troubleshooting Linux, Windows và "
            "các hệ quản trị MySQL/MariaDB, PostgreSQL, MongoDB, Redis.\n"
            "- Kinh nghiệm với HP OneView, IBM Spectrum, VMware vRealize, "
            "Prometheus, Grafana, ELK.\n"
            "- Có chứng chỉ LPI, CCNA hoặc chứng chỉ quản trị "
            "Linux/Windows/Solaris/AIX tương đương.\n"
            "Kỹ năng cần có:\n"
            "- VMware; Microsoft solutions (Active Directory, DNS, DHCP, "
            "FileServer, WSUS); Networking basics; Security solutions "
            "(Trend Micro, KAS); Linux (Ubuntu, CentOS); "
            "Basic programming (Python, Bash script)."
        ),
        "benefit": (
            "- Tham gia chương trình Training On-the-Job dành riêng cho "
            "vị trí, được đào tạo chuyên sâu về OpenStack, Linux, "
            "kiến trúc Cloud, ảo hóa, máy chủ, Storage, Network, HA, DR.\n"
            "- Trực tiếp tham gia triển khai các dự án Cloud thực tế, "
            "cấu hình, cài đặt, tích hợp, vận hành và tối ưu hạ tầng.\n"
            "- Tham gia xử lý sự cố thực tế, phân tích nguyên nhân gốc "
            "(Root Cause Analysis) và tối ưu hiệu năng hệ thống.\n"
            "- Hưởng các chế độ BHYT, BHXH, BHTN theo quy định.\n"
            "- Du lịch, nghỉ mát, bảo hiểm sức khỏe, bảo hiểm nhân thọ "
            "cho nhân sự xuất sắc và thưởng theo kết quả kinh doanh."
        ),
        "experience":  "Dưới 1 năm",
        "level": "FRESHER",
        "quantity": 5,
        "work_mode": "ONSITE",
        "job_type": "FULL_TIME",
        # Mức lương thỏa thuận, không tự đặt số.
        "min_salary": None,
        "max_salary": None,
        "location": (
            "85 Vũ Trọng Phụng, Thanh Xuân, Phường Thanh Xuân, Hà Nội"
        ),
        "working_time": "Thứ 2 - Thứ 6 (08:00 - 17:30)",
        "application_deadline": date(2026, 11, 16),
        "skills": {
            "Active Directory": "REQUIRED",
            "Python": "REQUIRED",
            "VMware": "REQUIRED",
            "Linux": "REQUIRED",
            "DHCP": "REQUIRED",
            "DNS": "REQUIRED",
            "PostgreSQL": "PREFERRED",
            "Prometheus": "PREFERRED",
            "MongoDB": "PREFERRED",
            "Grafana": "PREFERRED",
            "Windows": "PREFERRED",
            "MySQL": "PREFERRED",
            "Redis": "PREFERRED",
        },
    },

    {
        "company_name": "VIETTEL SOLUTIONS",
        "job_title": "IT Project Manager",
        "category_name": "IT Project Management",
        "job_description": (
            "- Quản lý nhiều dự án CNTT hoặc các dự án liên quan đến nhau, "
            "bao gồm các dự án chuyển đổi.\n"
            "- Làm việc với Product Owner để xác định yêu cầu, "
            "mong muốn của khách hàng về sản phẩm/dịch vụ.\n"
            "- Khởi tạo dự án: xác định mục tiêu, phạm vi công việc, "
            "nguồn lực dự kiến và các bên liên quan.\n"
            "- Lập kế hoạch dự án dựa trên phạm vi công việc, chi phí "
            "và các mốc hoàn thành. Phân chia công việc, sắp xếp "
            "thứ tự thực hiện và đề xuất nhân sự.\n"
            "- Đề xuất tiêu chuẩn và số lượng nhân sự tham gia dự án "
            "theo từng giai đoạn.\n"
            "- Quản lý tiến độ, chất lượng dự án và đánh giá "
            "hiệu suất của các thành viên.\n"
            "- Kiểm soát tiến độ công việc theo kế hoạch, "
            "đảm bảo tuân thủ quy trình thực hiện dự án.\n"
            "- Quản lý các vấn đề và rủi ro về tiến độ, nhân sự, "
            "chi phí, môi trường dự án; đề xuất giải pháp xử lý "
            "và phòng tránh rủi ro.\n"
            "- Quản lý doanh thu, chi phí của dự án.\n"
            "- Quản lý đối tác outsource nhằm đảm bảo tiến độ, "
            "chất lượng và quy trình của Tập đoàn.\n"
            "- Phối hợp với QA, QC để đánh giá quy trình "
            "và chất lượng hệ thống.\n"
            "- Thực hiện nghiệm thu với khách hàng.\n"
            "- Thực hiện các thủ tục kết thúc dự án."
        ),
        "job_requirement": (
            "- Tốt nghiệp Đại học chuyên ngành CNTT "
            "hoặc các chuyên ngành liên quan.\n"
            "- Có tối thiểu 4 năm kinh nghiệm phát triển dự án CNTT.\n"
            "- Có kiến thức quản trị dự án, có chứng chỉ PMI-ACP "
            "hoặc các chứng chỉ liên quan.\n"
            "- Có tinh thần cam kết và trách nhiệm trong công việc.\n"
            "- Nắm vững quy trình phát triển phần mềm "
            "hoặc có chứng chỉ về phương pháp phát triển Agile.\n"
            "- Có kiến thức về UI/UX và trải nghiệm người dùng.\n"
            "- Nắm vững kiến thức nghiệp vụ chuyên ngành "
            "của sản phẩm phụ trách.\n"
            "- Kỹ năng cần có: IT Project Management."
        ),
        "benefit": (
            "- Gói tổng thu nhập năm cạnh tranh, "
            "review lương định kỳ vào tháng 3 hằng năm.\n"
            "- Bảo hiểm sức khỏe và tai nạn cá nhân của Bảo Việt.\n"
            "- Khám sức khỏe định kỳ hằng năm.\n"
            "- Chế độ hỗ trợ đặc biệt dành cho nhân viên nữ "
            "trong thời gian nghỉ thai sản.\n"
            "- Giải thưởng ghi nhận năng lực và những đóng góp nổi bật.\n"
            "- Tài trợ 100% chi phí thi chứng chỉ chuyên môn quốc tế "
            "theo chính sách; hỗ trợ 50% chi phí thi lại theo quy định.\n"
            "- Được cung cấp tài khoản Udemy Elearning và tham gia "
            "các chương trình đào tạo, hội thảo chuyên ngành.\n"
            "- Cơ hội làm việc với khách hàng trong nước và quốc tế.\n"
            "- Làm việc tại văn phòng hạng A, tòa Landmark 72, "
            "có không gian xanh, khu vực gym và giải trí.\n"
            "- Tham gia Happy Hours 30 phút mỗi ngày "
            "(16:00 - 16:30) và các hoạt động thể thao.\n"
            "- Có 12 ngày phép hằng năm, 3 ngày nghỉ mát "
            "và 1 ngày lễ truyền thống 22/12 của Viettel.\n"
            "- Quà sinh nhật, teambuilding, Year End Party, "
            "nghỉ mát và các sự kiện nội bộ.\n"
            "- Các hoạt động quan tâm đến gia đình nhân viên "
            "vào những dịp đặc biệt."
        ),
        "experience": "4 năm",
        "level": "SENIOR",
        "quantity": 1,
        "work_mode": "ONSITE",
        "job_type": "FULL_TIME",
        # Lương thỏa thuận, không tự đặt mức lương.
        "min_salary": None,
        "max_salary": None,
        "location": (
            "Tòa nhà Landmark 72, Phạm Hùng, "
            "Phường Từ Liêm, Hà Nội"
        ),
        "working_time": (
            "Thứ 2 - Thứ 6, giờ làm việc linh hoạt: "
            "08:30 - 09:00 đến 18:00 - 18:30"
        ),
        "application_deadline": date(2026, 11, 13),
        "skills": {
            "Agile": "REQUIRED",
        },
    },





]


def seed_jobs():
    """Thêm JD và kỹ năng, không tạo trùng khi chạy lại."""
    created = 0

    try:
        for item in JOBS:
            company = Company.query.filter_by(
                company_name=item["company_name"]
            ).first()

            if company is None:
                raise ValueError(
                    f"Chưa có công ty: {item['company_name']}"
                )

            category = JobCategory.query.filter_by(
                category_name=item["category_name"]
            ).first()

            if category is None:
                raise ValueError(
                    f"Chưa có danh mục: {item['category_name']}"
                )

            # Xác định tin đã tồn tại theo công ty và tiêu đề.
            job = Job.query.filter_by(
                company_id=company.company_id,
                job_title=item["job_title"],
            ).first()

            if job is not None:
                print(f"Đã tồn tại, bỏ qua: {job.job_title}")
                continue

            # Kiểm tra toàn bộ kỹ năng trước khi tạo JD.
            selected_skills = []

            for skill_name, requirement_type in item["skills"].items():
                skill = Skill.query.filter_by(
                    skill_name=skill_name,
                    skill_status="ACTIVE",
                ).first()

                if skill is None:
                    raise ValueError(
                        f"Chưa có kỹ năng ACTIVE: {skill_name}"
                    )

                selected_skills.append((skill, requirement_type))

            job = Job(
                company_id=company.company_id,
                job_category_id=category.job_category_id,
                job_title=item["job_title"],
                job_description=item["job_description"],
                job_requirement=item["job_requirement"],
                job_slug=generate_job_slug(item["job_title"]),
                benefit=item["benefit"],
                experience=item["experience"],
                level=item["level"],
                quantity=item["quantity"],
                work_mode=item["work_mode"],
                job_type=item["job_type"],
                min_salary=item["min_salary"],
                max_salary=item["max_salary"],
                location=item["location"],
                working_time=item["working_time"],
                application_deadline=item["application_deadline"],
                job_status="OPEN",
                is_hidden=False,
            )

            db.session.add(job)
            db.session.flush()

            # Chỉ liên kết kỹ năng đã tồn tại trong bảng skills.
            for skill, requirement_type in selected_skills:
                db.session.add(
                    JobSkill(
                        job_id=job.job_id,
                        skill_id=skill.skill_id,
                        requirement_type=requirement_type,
                    )
                )

            created += 1
            print(f"Đã chuẩn bị: {job.job_title}")

        db.session.commit()
        print(f"Hoàn tất seed jobs. Số JD mới: {created}")

    except Exception:
        db.session.rollback()
        raise


def main():
    app = create_app()

    with app.app_context():
        seed_jobs()


if __name__ == "__main__":
    main()

