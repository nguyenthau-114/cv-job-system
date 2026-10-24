
from datetime import datetime, timezone

from flask import Blueprint, render_template, session, request, flash, redirect, url_for, send_file, jsonify

from app.extensions import db
from app.middleware.auth_middleware import role_required
from app.models.candidate_skill import CandidateSkill
from app.models.skill import Skill
from app.services.cv_service import (
    get_user_cvs,
    get_user_cv,
    upload_cv,
    delete_cv,
    set_cv_visibility,
    save_extracted_text
)
from app.services.skill_extractor import extract_skills
from app.services.fuzzy_matcher import extract_fuzzy_skills_db, get_fuzzy_context
from app.services.application_service import submit_application, replace_application_cv

candidate_bp = Blueprint("candidate", __name__, url_prefix="/candidate")


@candidate_bp.route("/cvs/<int:cv_id>/visibility", methods=["POST"])
@role_required("CANDIDATE")
def change_cv_visibility(cv_id):
    """Nhận trạng thái tường minh để request gửi lại không đảo trạng thái CV."""
    if (
        request.files or set(request.form) - {"is_hidden", "csrf_token"}
        or any(len(request.form.getlist(key)) != 1 for key in request.form)
        or request.form.get("is_hidden") not in {"0", "1"}
    ):
        return jsonify(success=False, errors={"is_hidden": "Trạng thái CV không hợp lệ."}), 400
    is_hidden = request.form["is_hidden"] == "1"
    success, message = set_cv_visibility(session["user_id"], cv_id, is_hidden)
    if not success:
        return jsonify(success=False, errors={"cv": message}), 400
    return jsonify(success=True, is_hidden=is_hidden, message=message)


@candidate_bp.route("/applications/<int:application_id>/cv", methods=["POST"])
@role_required("CANDIDATE")
def change_application_cv(application_id):
    """Chỉ nhận CV đã lưu, không nhận trạng thái hoặc thông tin liên hệ mới."""
    if (
        request.files or set(request.form) - {"cv_id", "csrf_token"}
        or any(len(request.form.getlist(key)) != 1 for key in request.form)
    ):
        return jsonify(success=False, errors={"cv_id": "Chỉ được chọn một CV đã lưu."}), 400
    result, errors = replace_application_cv(
        session["user_id"], application_id, request.form.get("cv_id")
    )
    if errors:
        statuses = {"account": 403, "application": 404, "state": 409, "concurrency": 409, "database": 503}
        return jsonify(success=False, errors=errors), statuses.get(next(iter(errors)), 400)
    return jsonify(success=True, **result)


@candidate_bp.route("/jobs/<int:job_id>/apply", methods=["POST"])
@role_required("CANDIDATE")
def apply_job(job_id):
    """Backend dùng chung cho form ở danh sách và chi tiết trong giai đoạn sau."""
    if request.files:
        return jsonify(success=False, errors={
            "cv_id": "Chỉ chọn CV đã lưu. Không tải CV mới trong form ứng tuyển."
        }), 400
    application, errors = submit_application(session["user_id"], job_id, request.form)
    if errors:
        return jsonify(
            success=False, errors=errors, manage_cvs_url=url_for("candidate.my_cvs")
        ), 400
    return jsonify(
        success=True, application_id=application.application_id,
        message="Ứng tuyển thành công."
    ), 201


@candidate_bp.route("/")
@role_required("CANDIDATE")
def dashboard():
    """Trang tổng quan Candidate."""
    return render_template("candidate/dashboard.html")


@candidate_bp.route("/cvs")
@role_required("CANDIDATE")
def my_cvs():
    """Danh sách CV của Candidate."""
    cvs = get_user_cvs(session.get("user_id"))
    return render_template("candidate/cvs.html", cvs=cvs, view_mode="list")


@candidate_bp.route("/cvs/upload", methods=["POST"])
@role_required("CANDIDATE")
def upload_cv_file():
    """Tải CV lên hệ thống."""
    success, result = upload_cv(
        session.get("user_id"),
        request.files.get("cv_file")
    )

    if not success:
        flash(result, "danger")
        return redirect(url_for("candidate.my_cvs"))

    flash("Tải CV lên thành công.", "success")
    return redirect(url_for("candidate.my_cvs"))


@candidate_bp.route("/cvs/<int:cv_id>/view")
@role_required("CANDIDATE")
def view_cv(cv_id):
    """Xem CV thuộc tài khoản đang đăng nhập."""
    cv = get_user_cv(session.get("user_id"), cv_id)

    if cv is None:
        flash("Không tìm thấy CV hoặc bạn không có quyền xem.", "danger")
        return redirect(url_for("candidate.my_cvs"))

    return send_file(
        cv.file_path,
        mimetype="application/pdf" if cv.file_type == "PDF" else None,
        as_attachment=False,
        download_name=cv.file_name
    )


@candidate_bp.route("/cvs/<int:cv_id>/analyze", methods=["POST"])
@role_required("CANDIDATE")
def analyze_cv(cv_id):
    """Trích xuất nội dung CV và chuyển sang xác nhận kỹ năng."""
    cv = get_user_cv(session.get("user_id"), cv_id)

    if cv is None:
        flash("Không tìm thấy CV hoặc bạn không có quyền phân tích.", "danger")
        return redirect(url_for("candidate.my_cvs"))

    # Không trích xuất lại khi CV đã được xác nhận
    if cv.analysis_status == "COMPLETED" and cv.extracted_text:
        return redirect(url_for("candidate.review_cv_skills", cv_id=cv_id))

    success, result = save_extracted_text(cv)

    if not success:
        flash(result, "danger")
        return redirect(url_for("candidate.my_cvs"))

    return redirect(url_for("candidate.review_cv_skills", cv_id=cv_id))


def get_cv_skill_results(cv):
    """Nhận diện Exact/Alias và lấy gợi ý Fuzzy."""
    exact_skills = extract_skills(cv.extracted_text)
    fuzzy_skills = extract_fuzzy_skills_db(cv.extracted_text, exact_skills)

    for skill in fuzzy_skills:
        skill["context"] = get_fuzzy_context(
            cv.extracted_text,
            skill["extracted_name"]
        )

    return exact_skills, fuzzy_skills


@candidate_bp.route("/cvs/<int:cv_id>/skills")
@role_required("CANDIDATE")
def review_cv_skills(cv_id):
    """Hiển thị giao diện xác nhận kỹ năng trong cvs.html."""
    cv = get_user_cv(session.get("user_id"), cv_id)

    if cv is None:
        flash("Không tìm thấy CV hoặc bạn không có quyền truy cập.", "danger")
        return redirect(url_for("candidate.my_cvs"))

    if not cv.extracted_text:
        flash("Vui lòng phân tích CV trước.", "warning")
        return redirect(url_for("candidate.my_cvs"))

    exact_skills, fuzzy_skills = get_cv_skill_results(cv)

    # Lấy kỹ năng đã lưu để hỗ trợ chỉnh sửa lần sau
    saved_skills = CandidateSkill.query.filter_by(cv_id=cv.cv_id).all()
    saved_ids = {item.skill_id for item in saved_skills}
    saved_manual_ids = {
        item.skill_id for item in saved_skills if item.source == "MANUAL"
    }

    # Danh mục kỹ năng chuẩn để Candidate bổ sung
    all_skills = Skill.query.filter_by(
        skill_status="ACTIVE"
    ).order_by(Skill.skill_name).all()

    return render_template(
        "candidate/cvs.html",
        view_mode="skills",
        cv=cv,
        exact_skills=exact_skills,
        fuzzy_skills=fuzzy_skills,
        all_skills=all_skills,
        saved_skills=saved_skills,
        saved_ids=saved_ids,
        saved_manual_ids=saved_manual_ids,
        is_confirmed=cv.analysis_status == "COMPLETED"
    )


@candidate_bp.route("/cvs/<int:cv_id>/skills/confirm", methods=["POST"])
@role_required("CANDIDATE")
def confirm_cv_skills(cv_id):
    """Kiểm tra và lưu kỹ năng đã xác nhận cùng nguồn gốc."""
    cv = get_user_cv(session.get("user_id"), cv_id)

    if cv is None:
        flash("Không tìm thấy CV hoặc bạn không có quyền truy cập.", "danger")
        return redirect(url_for("candidate.my_cvs"))

    if not cv.extracted_text:
        flash("Vui lòng phân tích CV trước.", "warning")
        return redirect(url_for("candidate.my_cvs"))

    exact_skills, fuzzy_skills = get_cv_skill_results(cv)

    # Kỹ năng nhận diện trực tiếp từ CV
    allowed_skills = {}

    for item in exact_skills:
        allowed_skills[str(item["skill_id"])] = {
            "name": item["extracted_name"],
            "source": "EXACT"
        }

    for item in fuzzy_skills:
        skill_id = str(item["skill_id"])
        if skill_id not in allowed_skills:
            allowed_skills[skill_id] = {
                "name": item["extracted_name"],
                "source": "FUZZY"
            }

    # Chỉ cho phép bổ sung kỹ năng có trong danh mục ACTIVE
    active_skills = Skill.query.filter_by(skill_status="ACTIVE").all()
    skill_lookup = {str(skill.skill_id): skill for skill in active_skills}

    selected_ids = set(request.form.getlist("skill_ids"))
    manual_ids = set(request.form.getlist("manual_skill_ids"))

    if not selected_ids.issubset(allowed_skills.keys()):
        flash("Danh sách kỹ năng nhận diện không hợp lệ.", "danger")
        return redirect(url_for("candidate.review_cv_skills", cv_id=cv_id))

    if not manual_ids.issubset(skill_lookup.keys()):
        flash("Danh sách kỹ năng bổ sung không hợp lệ.", "danger")
        return redirect(url_for("candidate.review_cv_skills", cv_id=cv_id))

    # Hợp nhất kỹ năng, tránh lưu trùng skill_id
    confirmed_skills = {
        skill_id: allowed_skills[skill_id]
        for skill_id in selected_ids
    }

    for skill_id in manual_ids:
        if skill_id not in confirmed_skills:
            confirmed_skills[skill_id] = {
                "name": skill_lookup[skill_id].skill_name,
                "source": "MANUAL"
            }

    try:
        # Thay thế danh sách cũ trong cùng một transaction
        CandidateSkill.query.filter_by(cv_id=cv.cv_id).delete(
            synchronize_session=False
        )

        for skill_id, item in confirmed_skills.items():
            db.session.add(CandidateSkill(
                cv_id=cv.cv_id,
                skill_id=int(skill_id),
                extracted_name=item["name"],
                source=item["source"]
            ))

        cv.analysis_status = "COMPLETED"
        cv.analyzed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

    except Exception:
        db.session.rollback()
        flash("Không thể lưu kỹ năng. Vui lòng thử lại.", "danger")
        return redirect(url_for("candidate.review_cv_skills", cv_id=cv_id))

    flash(f"Đã xác nhận và lưu {len(confirmed_skills)} kỹ năng.", "success")
    return redirect(url_for("candidate.my_cvs"))


@candidate_bp.route("/cvs/<int:cv_id>/delete", methods=["POST"])
@role_required("CANDIDATE")
def delete_cv_file(cv_id):
    """Xóa CV thuộc Candidate đang đăng nhập."""
    success, message = delete_cv(session.get("user_id"), cv_id)

    flash(message, "success" if success else "danger")
    return redirect(url_for("candidate.my_cvs"))
