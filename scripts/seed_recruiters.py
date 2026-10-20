
import os
import secrets
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from flask import current_app

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.company import Company


# Thư mục chứa ảnh nguồn của dữ liệu mẫu
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

RECRUITER = {
    "user_name": "Nguyễn Minh Khang",
    "email": "recruiter01@jobfit.test",
    "avatar_source": "recruiter01.jpg",
}

COMPANY = {
    "company_name": "VIETTEL SOLUTIONS",
    "company_description": (
        "Tổng Công ty Giải pháp Doanh nghiệp Viettel, đơn vị thuộc "
        "Tập đoàn Công nghiệp - Viễn thông Quân đội, cung cấp "
        "các giải pháp công nghệ thông tin và chuyển đổi số "
        "cho doanh nghiệp, tổ chức và cơ quan nhà nước."
    ),
    "address": "Số 1 Trần Hữu Dực, Mỹ Đình 2, Nam Từ Liêm, Hà Nội",
    "website": "https://solutions.viettel.vn/",
    "logo_source": "viettel_solutions.jpg",
}


def save_seed_image(source_name, folder_name, prefix, output_format):
    """Chuẩn hóa ảnh theo quy tắc upload hiện tại của JobFit."""
    source = ASSETS_DIR / source_name

    if not source.is_file():
        raise FileNotFoundError(f"Không tìm thấy ảnh nguồn: {source}")

    if source.stat().st_size > 3 * 1024 * 1024:
        raise ValueError(f"Ảnh vượt quá 3 MB: {source_name}")

    # Chỉ cho phép ảnh JPG, PNG hoặc WebP hợp lệ
    try:
        with Image.open(source) as image:
            image.verify()

        with Image.open(source) as image:
            if image.format not in ("JPEG", "PNG", "WEBP"):
                raise ValueError(f"Định dạng ảnh không hỗ trợ: {source_name}")

            if image.width * image.height > 20_000_000:
                raise ValueError(f"Ảnh có kích thước quá lớn: {source_name}")

            mode = "RGBA" if output_format == "PNG" else "RGB"
            image = image.convert(mode)
            image.thumbnail((512, 512))

            folder = Path(current_app.static_folder) / "uploads" / folder_name
            folder.mkdir(parents=True, exist_ok=True)

            extension = "png" if output_format == "PNG" else "jpg"
            filename = f"{prefix}_{secrets.token_hex(16)}.{extension}"
            destination = folder / filename

            if output_format == "PNG":
                image.save(destination, format="PNG", optimize=True)
            else:
                image.save(destination, format="JPEG", quality=85)

            return f"uploads/{folder_name}/{filename}"

    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError(f"Không thể xử lý ảnh {source_name}") from exc


def seed_viettel():
    """Tạo Recruiter 01 và công ty, không ghi đè dữ liệu đã tồn tại."""
    created_images = []

    try:
        email = RECRUITER["email"]

        recruiter = User.query.filter_by(email=email).first()
        company_by_name = Company.query.filter_by(
            company_name=COMPANY["company_name"]
        ).first()

        # Kiểm tra trước để tránh chiếm quyền sở hữu công ty có sẵn
        if recruiter is not None and recruiter.role != "RECRUITER":
            raise ValueError("Email đã thuộc tài khoản không phải Recruiter.")

        if company_by_name is not None:
            if recruiter is None or company_by_name.user_id != recruiter.user_id:
                raise ValueError("Tên công ty đã thuộc tài khoản khác.")

        if recruiter is None:
            password = os.getenv("SEED_RECRUITER_PASSWORD")

            if not password:
                raise ValueError(
                    "Chưa cấu hình SEED_RECRUITER_PASSWORD trong .env."
                )

            recruiter = User(
                user_name=RECRUITER["user_name"],
                email=email,
                role="RECRUITER",
                user_status="ACTIVE",
                email_verified=True,
            )

            # Dùng phương thức băm mật khẩu có sẵn trong Model
            recruiter.set_password(password)
            db.session.add(recruiter)
            db.session.flush()
            print(f"Đã tạo Recruiter: {recruiter.email}")
        else:
            print(f"Recruiter đã tồn tại: {recruiter.email}")

        company = Company.query.filter_by(
            user_id=recruiter.user_id
        ).first()

        if company is None:
            company = Company(
                user_id=recruiter.user_id,
                company_name=COMPANY["company_name"],
                company_description=COMPANY["company_description"],
                address=COMPANY["address"],
                website=COMPANY["website"],
            )
            db.session.add(company)
            db.session.flush()
            print(f"Đã tạo công ty: {company.company_name}")

        elif company.company_name != COMPANY["company_name"]:
            raise ValueError("Recruiter đang sở hữu công ty khác.")

        else:
            print(f"Công ty đã tồn tại: {company.company_name}")

        # Chỉ thêm avatar khi tài khoản chưa có ảnh
        if not recruiter.avatar:
            avatar_path = save_seed_image(
                RECRUITER["avatar_source"],
                "avatars",
                "avatar",
                "JPEG",
            )
            created_images.append(avatar_path)
            recruiter.avatar = avatar_path

        # Chỉ thêm logo khi công ty chưa có ảnh
        if not company.logo:
            logo_path = save_seed_image(
                COMPANY["logo_source"],
                "companies",
                "company",
                "PNG",
            )
            created_images.append(logo_path)
            company.logo = logo_path

        db.session.commit()

        print("\nSEED VIETTEL THÀNH CÔNG")
        print(f"Recruiter ID: {recruiter.user_id}")
        print(f"Email: {recruiter.email}")
        print(f"Avatar: {recruiter.avatar}")
        print(f"Company ID: {company.company_id}")
        print(f"Công ty: {company.company_name}")
        print(f"Logo: {company.logo}")

    except Exception:
        db.session.rollback()

        # Nếu lưu thất bại, xóa ảnh mới để tránh file rác
        for relative_path in created_images:
            path = Path(current_app.static_folder) / relative_path
            path.unlink(missing_ok=True)

        raise


def main():
    app = create_app()

    with app.app_context():
        seed_viettel()


if __name__ == "__main__":
    main()
