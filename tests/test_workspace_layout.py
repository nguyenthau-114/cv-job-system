"""Kiểm thử layout bằng dữ liệu giả trên SQLite RAM, không đọc .env/MySQL."""
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from flask import render_template
from jinja2 import ChoiceLoader, DictLoader, meta
from sqlalchemy import MetaData, Text, event


safe_config = ModuleType("config")
safe_config.Config = type("TestConfig", (), {})
previous_config = sys.modules.get("config")
sys.modules["config"] = safe_config
try:
    import app as app_package
    from app.extensions import db
    from app.models.company import Company
    from app.models.cv import CV
    from app.models.job import Job
    from app.models.job_category import JobCategory
    from app.models.skill import Skill
    from app.models.user import User
finally:
    if previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = previous_config


ROOT = Path(__file__).resolve().parents[1]


class TestConfig:
    TESTING = True
    SECRET_KEY = "workspace-layout-tests-only"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True
    MAIL_SUPPRESS_SEND = True


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def find(self, tag=None, **attrs):
        return [item for name, item in self.elements
                if (tag is None or name == tag)
                and all(item.get(key) == value for key, value in attrs.items())]


class WorkspaceLayoutTests(unittest.TestCase):
    def setUp(self):
        # Factory thật, cấu hình test được thay trước khi tạo engine.
        with patch.object(app_package, "Config", TestConfig):
            self.app = app_package.create_app()
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        self.assertEqual(db.engine.url.get_backend_name(), "sqlite")
        self.assertEqual(db.engine.url.database, ":memory:")

        @event.listens_for(db.engine, "connect")
        def sqlite_functions(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            # Hàm ngày MySQL của dashboard Admin, chỉ mô phỏng trong test.
            connection.create_function("year", 1, lambda value: int(value[:4]) if value else None)
            connection.create_function("month", 1, lambda value: int(value[5:7]) if value else None)

        metadata = MetaData()
        for table in db.metadata.sorted_tables:
            table.to_metadata(metadata)
        metadata.tables["cvs"].c.extracted_text.type = Text()
        metadata.create_all(db.engine)
        self.candidate = User(user_name="Test candidate", email="candidate@example.invalid",
                              password_hash="unused", role="CANDIDATE", email_verified=True)
        self.recruiter = User(user_name="Test recruiter", email="recruiter@example.invalid",
                              password_hash="unused", role="RECRUITER", email_verified=True)
        self.admin = User(user_name="Test admin", email="admin@example.invalid",
                          password_hash="unused", role="ADMIN", email_verified=True)
        self.category = JobCategory(category_name="Synthetic category")
        self.skill = Skill(skill_name="Synthetic skill")
        db.session.add_all([self.candidate, self.recruiter, self.admin, self.category, self.skill])
        db.session.flush()
        self.company = Company(user_id=self.recruiter.user_id, company_name="Synthetic company")
        db.session.add(self.company)
        db.session.flush()
        self.job = Job(company_id=self.company.company_id, job_category_id=self.category.job_category_id,
                       job_title="Synthetic job", job_description="Synthetic JD", job_requirement="Requirement",
                       experience="1 year", level="JUNIOR", quantity=1, work_mode="ONSITE",
                       job_type="FULL_TIME", location="Synthetic location", job_slug="synthetic-job",
                       application_deadline=date.today() + timedelta(days=30))
        self.cv = CV(user_id=self.candidate.user_id, file_name="synthetic.pdf", file_path="not-a-real-file",
                     file_type="PDF")
        db.session.add_all([self.job, self.cv])
        db.session.commit()
        self.client = self.app.test_client()

    def login(self, user=None):
        with self.client.session_transaction() as current:
            current.clear()
            if user is not None:
                current["user_id"] = user.user_id
                current["role"] = user.role

    def get_html(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def active_links(self, html, role):
        return [item for item in Elements(html).find("a")
                if role + "-nav-link" in item.get("class", "").split()
                and "active" in item.get("class", "").split()]

    def test_all_jinja_references_resolve_and_old_layout_paths_are_absent(self):
        env = self.app.jinja_env
        names = env.list_templates()
        self.assertNotIn("base.html", names)
        self.assertNotIn("admin/base_admin.html", names)
        for name in names:
            with self.subTest(template=name):
                source = env.loader.get_source(env, name)[0]
                parsed = env.parse(source)
                env.get_template(name)
                for reference in meta.find_referenced_templates(parsed):
                    self.assertIsNotNone(reference)
                    self.assertNotIn(reference, {"base.html", "admin/base_admin.html"})
                    env.get_template(reference)

    def test_public_pages_render_without_workspace(self):
        for user in (None, self.candidate, self.recruiter):
            self.login(user)
            for path in ("/", "/jobs", f"/jobs/{self.job.job_id}"):
                with self.subTest(user=user.role if user else "guest", path=path):
                    html = self.get_html(path)
                    self.assertNotIn('class="workspace-layout', html)
                    self.assertNotIn("css/workspace.css", html)
                    self.assertIn("bootstrap.bundle.min.js", html)

    def test_all_auth_templates_render_and_keep_csrf(self):
        self.login()
        for path in ("/auth/login", "/auth/register", "/auth/forgot-password"):
            with self.subTest(path=path):
                html = self.get_html(path)
                self.assertTrue(Elements(html).find("input", name="csrf_token"))
                self.assertNotIn("css/workspace.css", html)
        with self.client.session_transaction() as current:
            current.update(verify_user_id=self.candidate.user_id, verify_otp="synthetic-only",
                           verify_otp_expires_at=9999999999,
                           setup_recruiter_user_id=self.recruiter.user_id)
        for path in ("/auth/verify-email", "/auth/register/recruiter/company"):
            self.assertTrue(Elements(self.get_html(path)).find("input", name="csrf_token"))
        # Các nhánh OTP/reset dùng cùng template, kiểm tra cả block điều kiện.
        for mode in ("request", "verify", "reset"):
            with self.subTest(mode=mode), self.app.test_request_context("/auth/forgot-password"):
                html = render_template("auth/forgot_password.html", mode=mode)
                self.assertIn("</html>", html)

    def test_candidate_dashboard_and_cv_pages_render_with_active_menu(self):
        self.login(self.candidate)
        for path, href in (("/candidate/", "/candidate/"), ("/candidate/cvs", "/candidate/cvs")):
            with self.subTest(path=path):
                html = self.get_html(path)
                active = self.active_links(html, "workspace")
                self.assertEqual([item["href"] for item in active], [href])
                self.assertEqual(active[0].get("aria-current"), "page")
                self.assertIn('id="candidateSidebar"', html)
                self.assertIn("Tìm việc làm", html)
                self.assertNotIn("Thông tin công ty", html)

    def test_cv_list_keeps_upload_analyze_delete_forms_and_csrf(self):
        self.login(self.candidate)
        html = self.get_html("/candidate/cvs")
        elements = Elements(html)
        for action in ("/candidate/cvs/upload", f"/candidate/cvs/{self.cv.cv_id}/analyze",
                       f"/candidate/cvs/{self.cv.cv_id}/delete"):
            self.assertTrue(elements.find("form", method="POST", action=action), action)
        self.assertTrue(elements.find("form", enctype="multipart/form-data"))
        self.assertTrue(elements.find("input", type="file", name="cv_file"))
        self.assertGreaterEqual(len(elements.find("input", name="csrf_token")), 3)
        self.assertEqual(self.client.post(f"/candidate/cvs/{self.cv.cv_id}/delete").status_code, 400)
        self.assertIsNotNone(db.session.get(CV, self.cv.cv_id))

    def test_empty_cv_page_keeps_upload_form(self):
        db.session.delete(self.cv)
        db.session.commit()
        self.login(self.candidate)
        html = self.get_html("/candidate/cvs")
        self.assertIn("Chưa có CV nào", html)
        self.assertTrue(Elements(html).find("form", action="/candidate/cvs/upload"))

    def test_cv_analysis_states_keep_existing_actions(self):
        self.login(self.candidate)
        for status, text, label in (
            ("PENDING", None, "Phân tích CV"),
            ("FAILED", None, "Phân tích"),
            ("PENDING", "Synthetic skill", "Tiếp tục xác nhận"),
            ("COMPLETED", "Synthetic skill", "Xem kỹ năng"),
        ):
            with self.subTest(status=status, extracted=bool(text)):
                self.cv.analysis_status = status
                self.cv.extracted_text = text
                db.session.commit()
                html = self.get_html("/candidate/cvs")
                self.assertIn(label, html)
                elements = Elements(html)
                self.assertTrue(elements.find("a", href=f"/candidate/cvs/{self.cv.cv_id}/view"))
                self.assertTrue(elements.find("form", action=f"/candidate/cvs/{self.cv.cv_id}/delete"))
                if text:
                    self.assertTrue(elements.find("a", href=f"/candidate/cvs/{self.cv.cv_id}/skills"))
                else:
                    self.assertTrue(elements.find("form", action=f"/candidate/cvs/{self.cv.cv_id}/analyze"))

    def test_cv_skills_mode_preserves_controls_and_javascript(self):
        self.cv.extracted_text = "Synthetic skill"
        db.session.commit()
        self.login(self.candidate)
        html = self.get_html(f"/candidate/cvs/{self.cv.cv_id}/skills")
        self.assertEqual([item["href"] for item in self.active_links(html, "workspace")], ["/candidate/cvs"])
        elements = Elements(html)
        self.assertTrue(elements.find("form", id="skillConfirmForm", method="POST",
                                      action=f"/candidate/cvs/{self.cv.cv_id}/skills/confirm"))
        for identifier in ("manualSkillSearch", "manualSkillResults", "manualSkillCatalog",
                           "manualSkillTags", "manualSkillInputs", "manualSkillEmpty"):
            self.assertTrue(elements.find(id=identifier), identifier)
        self.assertIn('document.getElementById("skillConfirmForm")', html)
        self.assertTrue(elements.find("input", name="csrf_token"))
        self.assertIn("bootstrap.bundle.min.js", html)

    def test_recruiter_pages_preserve_menu_content_and_offcanvas_ids(self):
        self.login(self.recruiter)
        for path, href in (("/recruiter/", "/recruiter/"), ("/recruiter/jobs", "/recruiter/jobs"),
                           (f"/recruiter/jobs/{self.job.job_id}", "/recruiter/jobs"),
                           ("/recruiter/jobs/create", "/recruiter/jobs/create"),
                           ("/recruiter/account", "/recruiter/account"),
                           ("/recruiter/company", "/recruiter/company")):
            with self.subTest(path=path):
                html = self.get_html(path)
                self.assertEqual([item["href"] for item in self.active_links(html, "recruiter")], [href])
                self.assertIn('id="recruiterSidebar"', html)
                self.assertNotIn('id="candidateSidebar"', html)

    def test_admin_pages_render_independent_layout(self):
        self.login(self.admin)
        for path in ("/admin/", "/admin/users", "/admin/jobs"):
            with self.subTest(path=path):
                html = self.get_html(path)
                self.assertIn('class="admin-body"', html)
                self.assertIn('id="adminMobileSidebar"', html)
                self.assertIn("css/admin.css", html)
                self.assertNotIn("css/workspace.css", html)
                self.assertNotIn("css/style.css", html)
                self.assertTrue(Elements(html).find("input", name="csrf_token"))

    def test_recruiter_skill_review_and_confirmation_blocks_render(self):
        data = {column.name: getattr(self.job, column.name) for column in Job.__table__.columns}
        data["application_deadline"] = self.job.application_deadline.isoformat()
        selected = [{"skill_id": self.skill.skill_id, "skill_name": self.skill.skill_name,
                     "requirement_type": "REQUIRED"}]
        for template, path, marker in (
            ("review_job_skills.html", "/recruiter/jobs/review-skills", "skillReviewForm"),
            ("confirm_job.html", "/recruiter/jobs/confirm", "publishJobForm"),
        ):
            with self.subTest(template=template), self.app.test_request_context(path, method="POST"):
                html = render_template("recruiter/" + template, data=data, company=self.company,
                                       category=self.category, detected_skills=selected,
                                       available_skills=[self.skill], selected_skills=selected,
                                       publish_token="synthetic-token")
                self.assertTrue(Elements(html).find("form", id=marker))
                self.assertTrue(Elements(html).find("input", name="csrf_token"))
                self.assertIn("css/workspace.css", html)
                self.assertIn("css/recruiter.css", html)
                self.assertIn("bootstrap.bundle.min.js", html)

    def test_resources_load_once_in_correct_inheritance_order(self):
        for user, path, expected in (
            (self.candidate, "/candidate/cvs", ["style.css", "workspace.css", "candidate.css"]),
            (self.recruiter, "/recruiter/jobs/create", ["style.css", "workspace.css", "recruiter.css"]),
            (self.admin, "/admin/jobs", ["admin.css"]),
        ):
            with self.subTest(path=path):
                self.login(user)
                elements = Elements(self.get_html(path))
                styles = [item["href"] for item in elements.find("link", rel="stylesheet")]
                scripts = [item["src"] for item in elements.find("script") if "src" in item]
                self.assertEqual(len(styles), len(set(styles)))
                self.assertEqual(len(scripts), len(set(scripts)))
                self.assertEqual([url.rsplit("/", 1)[-1] for url in styles if "/static/css/" in url], expected)
                self.assertEqual(sum("bootstrap.bundle.min.js" in url for url in scripts), 1)
                for url in styles:
                    if url.startswith("/static/"):
                        response = self.client.get(url)
                        self.assertEqual(response.status_code, 200)
                        response.close()

    def test_mobile_offcanvas_targets_and_accessible_labels_match(self):
        for user, path, sidebar in ((self.candidate, "/candidate/", "candidateSidebar"),
                                     (self.recruiter, "/recruiter/", "recruiterSidebar")):
            with self.subTest(sidebar=sidebar):
                self.login(user)
                elements = Elements(self.get_html(path))
                aside = elements.find("aside", id=sidebar)
                self.assertEqual(len(aside), 1)
                self.assertIn("offcanvas-lg", aside[0]["class"].split())
                self.assertTrue(elements.find(id=aside[0]["aria-labelledby"]))
                self.assertTrue(elements.find("button", **{"data-bs-toggle": "offcanvas",
                                                                         "data-bs-target": "#" + sidebar,
                                                                         "aria-controls": sidebar}))
                self.assertTrue(elements.find("button", **{"data-bs-dismiss": "offcanvas",
                                                                         "data-bs-target": "#" + sidebar}))

    def test_nested_style_script_and_role_content_blocks_survive(self):
        probe = """{% extends 'candidate/candidate_base.html' %}
{% block title %}Nested title{% endblock %}
{% block styles %}{{ super() }}<style id="probe-style"></style>{% endblock %}
{% block candidate_content %}<p id="probe-content">Nested content</p>{% endblock %}
{% block scripts %}{{ super() }}<script id="probe-script"></script>{% endblock %}"""
        env = self.app.jinja_env
        with patch.object(env, "loader", ChoiceLoader([DictLoader({"probe.html": probe}), env.loader])):
            env.cache.clear()
            with self.app.test_request_context("/candidate/"):
                html = render_template("probe.html")
            env.cache.clear()
        self.assertIn("<title>Nested title</title>", html)
        for marker in ("probe-style", "probe-content", "probe-script", "css/workspace.css", "css/candidate.css"):
            self.assertIn(marker, html)
        self.assertEqual(html.count("bootstrap.bundle.min.js"), 1)

    def test_flash_toast_and_recruiter_modal_survive(self):
        self.login(self.candidate)
        with self.client.session_transaction() as current:
            current["_flashes"] = [("success", "Synthetic success")]
        html = self.get_html("/candidate/")
        self.assertIn("Synthetic success", html)
        self.assertIn("bootstrap.Toast", html)
        self.assertIn("bi-check-circle-fill text-success", html)
        self.login(self.recruiter)
        html = self.get_html(f"/recruiter/jobs/{self.job.job_id}")
        elements = Elements(html)
        targets = [item["data-bs-target"] for item in elements.find("button")
                   if item.get("data-bs-toggle") == "modal"]
        self.assertTrue(targets)
        for target in targets:
            self.assertTrue(elements.find(id=target.lstrip("#")))
        self.assertTrue(elements.find("input", name="csrf_token"))


if __name__ == "__main__":
    unittest.main()
