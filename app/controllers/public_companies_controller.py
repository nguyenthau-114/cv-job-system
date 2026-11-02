from flask import Blueprint, abort, render_template, request, session

from app.services.public_job_service import get_public_company_page


public_companies_bp = Blueprint("public_companies", __name__)


@public_companies_bp.after_request
def private_company_response(response):
    # Card và CSRF phụ thuộc phiên đăng nhập dù hồ sơ công ty là công khai.
    response.headers["Cache-Control"] = "private, no-store"
    return response


@public_companies_bp.route("/companies/<int:company_id>")
def show(company_id):
    if not 1 <= company_id <= 2147483647:
        abort(404)
    data = get_public_company_page(company_id, session.get("user_id"), request.args.get("page", 1, type=int))
    if data is None:
        abort(404)
    return render_template("companies/show.html", **data)
