"""Kiểm thử riêng bằng SQLite trong RAM, không đọc .env hoặc chạy migration.

Chạy: .venv\Scripts\python.exe -B -m unittest tests.test_recruiter_job_edit -v
SQLite không xác nhận được hành vi SELECT FOR UPDATE của MySQL.
"""
import ast
from datetime import date, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch

from flask import Flask
from sqlalchemy import MetaData, Text, event, update
from sqlalchemy.dialects import mysql


# Chặn import config thật trước khi nạp package app, tránh load_dotenv().
safe_config = ModuleType("config")
safe_config.Config = type("TestConfig", (), {})
previous_config = sys.modules.get("config")
sys.modules["config"] = safe_config
try:
    from app.controllers import recruiter_controller as controller
    from app.extensions import csrf, db
    from app.models.application import Application
    from app.models.company import Company
    from app.models.cv import CV
    from app.models.job import Job
    from app.models.job_category import JobCategory
    from app.models.job_skill import JobSkill
    from app.models.skill import Skill
    from app.models.user import User
    from app.services.job_service import publish_job
finally:
    if previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = previous_config


ROOT = Path(__file__).resolve().parents[1]
WARNING = (
    "Bạn chỉ được chỉnh sửa thông tin tin tuyển dụng 1 lần duy nhất. "
    "Vui lòng kiểm tra kỹ trước khi lưu."
)


class FormParser(HTMLParser):
    """Kiểm tra các control được gắn đúng form HTML, kể cả form ngoài."""

    def __init__(self, html):
        super().__init__()
        self.forms = {}
        self.current = None
        self.nested = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.nested |= self.current is not None
            self.current = attrs.get("id", "anonymous")
            self.forms.setdefault(self.current, {"attrs": attrs, "controls": {}})
        elif tag in {"input", "textarea", "button"} and attrs.get("name"):
            owner = attrs.get("form", self.current)
            if owner:
                self.forms.setdefault(owner, {"attrs": {}, "controls": {}})
                self.forms[owner]["controls"][attrs["name"]] = attrs

    def handle_endtag(self, tag):
        if tag == "form":
            self.current = None


class RecruiterJobEditTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("job_edit_tests", root_path=str(ROOT / "app"))
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="job-edit-tests-only",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            WTF_CSRF_ENABLED=True,
        )
        db.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(controller.recruiter_bp)
        for endpoint, path in {
            "home.home": "/",
            "public_jobs.index": "/jobs",
            "auth.login": "/auth/login",
            "auth.register": "/auth/register",
            "auth.logout": "/auth/logout",
        }.items():
            self.app.add_url_rule(path, endpoint, lambda: "test")
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        self.assertEqual(db.engine.url.get_backend_name(), "sqlite")
        self.assertEqual(db.engine.url.database, ":memory:")

        @event.listens_for(db.engine, "connect")
        def enable_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        # Chỉ đổi LONGTEXT thành TEXT trong bản sao schema kiểm thử SQLite.
        metadata = MetaData()
        for table in db.metadata.sorted_tables:
            table.to_metadata(metadata)
        metadata.tables["cvs"].c.extracted_text.type = Text()
        metadata.create_all(db.engine)
        self.user = User(
            user_name="Recruiter test", email="recruiter@example.invalid",
            password_hash="unused", role="RECRUITER", email_verified=True
        )
        self.category = JobCategory(category_name="Test category")
        db.session.add_all([self.user, self.category])
        db.session.flush()
        self.company = Company(user_id=self.user.user_id, company_name="Test company")
        db.session.add(self.company)
        db.session.flush()
        self.job = Job(
            company_id=self.company.company_id,
            job_category_id=self.category.job_category_id,
            job_title="Original title", job_description="Original JD",
            job_requirement="Original requirements", experience="1 year", level="JUNIOR",
            quantity=3, work_mode="ONSITE", job_type="FULL_TIME",
            min_salary=Decimal("10000000.00"), max_salary=Decimal("20000000.00"),
            location="Original location", working_time="Mon-Fri", benefit="Line 1\nLine 2",
            application_deadline=date.today() + timedelta(days=30), job_slug="test-job"
        )
        db.session.add(self.job)
        db.session.commit()
        self.job_id = self.job.job_id
        self.url = f"/recruiter/jobs/{self.job_id}"
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user.user_id
            session["role"] = "RECRUITER"
        html = self.client.get(self.url + "?edit=1").get_data(as_text=True)
        self.token = FormParser(html).forms["editJobForm"]["controls"]["csrf_token"]["value"]

    def payload(self, **changes):
        data = {
            "action": "edit_content", "location": "New location",
            "min_salary": "10000000", "max_salary": "20000000",
            "working_time": "Mon-Fri", "benefit": "Line 1\nLine 2"
        }
        data.update(changes)
        return data

    def post(self, data, csrf_token=True):
        data = dict(data)
        if csrf_token:
            data["csrf_token"] = self.token
        return self.client.post(self.url + "/edit", data=data)

    def assert_original(self, count=0):
        db.session.expire_all()
        self.assertEqual(self.job.location, "Original location")
        self.assertEqual(self.job.content_edit_count, count)
        self.assertEqual(self.job.job_title, "Original title")
        self.assertEqual(self.job.job_description, "Original JD")
        self.assertEqual(self.job.job_requirement, "Original requirements")

    def add_application(self, status="SUBMITTED"):
        cv = CV(
            user_id=self.user.user_id, file_name="synthetic.pdf",
            file_path="not-used.pdf", file_type="PDF"
        )
        db.session.add(cv)
        db.session.flush()
        db.session.add(Application(
            cv_id=cv.cv_id, job_id=self.job_id,
            contact_email="candidate@example.invalid", application_status=status
        ))
        db.session.commit()

    def test_content_changes_once_and_survives_new_session(self):
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 302)
        db.session.expire_all()
        self.assertEqual(self.job.location, "New location")
        self.assertEqual(self.job.content_edit_count, 1)
        self.assertEqual(self.job.job_title, "Original title")
        self.assertEqual(self.job.job_description, "Original JD")
        self.assertEqual(self.job.job_requirement, "Original requirements")
        # Không thể lấy lại lượt bằng cách xóa dữ liệu session.
        with self.client.session_transaction() as session:
            session.clear()
            session["user_id"] = self.user.user_id
        html = self.client.get(self.url + "?edit=1").get_data(as_text=True)
        token = FormParser(html).forms["increaseQuantityForm"]["controls"]["csrf_token"]["value"]
        self.token = token
        self.post(self.payload(location="Second change"))
        db.session.expire_all()
        self.assertEqual(self.job.location, "New location")
        self.assertEqual(self.job.content_edit_count, 1)

    def test_exhausted_count_blocks_content(self):
        self.job.content_edit_count = 1
        db.session.commit()
        self.post(self.payload())
        self.assert_original(count=1)

    def test_any_application_including_withdrawn_blocks_content(self):
        for status in ("SUBMITTED", "WITHDRAWN"):
            with self.subTest(status=status):
                self.add_application(status)
                self.post(self.payload())
                self.assert_original()

    def test_open_and_cancel_do_not_consume_turn(self):
        self.assertEqual(self.client.get(self.url + "?edit=1").status_code, 200)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assert_original()

    def test_equivalent_values_do_not_consume_turn(self):
        response = self.post(self.payload(
            location="  Original location  ", min_salary="10000000.000",
            max_salary="2E7", working_time=" Mon-Fri ", benefit=" Line 1\r\nLine 2\r\n"
        ))
        self.assertEqual(response.status_code, 302)
        self.assert_original()
        with self.client.session_transaction() as session:
            self.assertIn("Không có thay đổi", session["_flashes"][-1][1])

    def test_blank_optional_fields_equal_null(self):
        self.job.min_salary = self.job.max_salary = None
        self.job.working_time = self.job.benefit = None
        db.session.commit()
        self.post(self.payload(
            location="Original location", min_salary="", max_salary="",
            working_time=" ", benefit="\r\n"
        ))
        self.assert_original()

    def test_commit_failure_rolls_back_content_and_counter(self):
        def fail_after_flush():
            db.session.flush()
            raise RuntimeError("test commit failure after writing")

        with patch.object(db.session, "commit", side_effect=fail_after_flush):
            with self.assertLogs(self.app.logger, level="ERROR"):
                self.post(self.payload())
        self.assert_original()

    def test_stale_counter_is_refreshed_before_saving(self):
        # Giữ object cũ trong identity map, còn giá trị database đã thành 1.
        self.assertEqual(self.job.content_edit_count, 0)
        current_session = db.session()
        previous_expiration = current_session.expire_on_commit
        try:
            current_session.expire_on_commit = False
            db.session.execute(update(Job).where(Job.job_id == self.job_id).values(
                content_edit_count=1
            ).execution_options(synchronize_session=False))
            db.session.commit()
            self.assertEqual(self.job.content_edit_count, 0)
            self.post(self.payload())
            self.assert_original(count=1)
        finally:
            current_session.expire_on_commit = previous_expiration

    def test_allowed_content_fields_change_together_and_preserve_skills(self):
        skill = Skill(skill_name="Synthetic skill")
        db.session.add(skill)
        db.session.flush()
        job_skill = JobSkill(job_id=self.job_id, skill_id=skill.skill_id, requirement_type="REQUIRED")
        db.session.add(job_skill)
        db.session.commit()
        original_skill = (job_skill.job_skill_id, job_skill.skill_id, job_skill.requirement_type)
        self.post(self.payload(
            min_salary="12000000", max_salary="25000000",
            working_time="New working time", benefit="New benefit"
        ))
        db.session.expire_all()
        self.assertEqual(self.job.min_salary, Decimal("12000000"))
        self.assertEqual(self.job.max_salary, Decimal("25000000"))
        self.assertEqual(self.job.working_time, "New working time")
        self.assertEqual(self.job.benefit, "New benefit")
        self.assertEqual(self.job.content_edit_count, 1)
        self.assertEqual((job_skill.job_skill_id, job_skill.skill_id, job_skill.requirement_type), original_skill)
        self.assertEqual(self.job.job_title, "Original title")
        self.assertEqual(self.job.job_description, "Original JD")
        self.assertEqual(self.job.job_requirement, "Original requirements")

    def test_newly_published_job_starts_open_with_zero_edits(self):
        self.job.content_edit_count = 1
        db.session.commit()
        data = {
            "job_title": "New job", "job_category_id": str(self.category.job_category_id),
            "job_description": "New JD", "job_requirement": "New requirements",
            "experience": "1 year", "level": "JUNIOR", "quantity": "2",
            "work_mode": "REMOTE", "job_type": "FULL_TIME", "min_salary": "",
            "max_salary": "", "location": "New location", "benefit": "", "working_time": "",
            "application_deadline": self.job.application_deadline.isoformat()
        }
        skill = Skill(skill_name="Publish skill")
        db.session.add(skill)
        db.session.commit()
        job = publish_job(self.company.company_id, data, [{
            "skill_id": skill.skill_id, "requirement_type": "REQUIRED"
        }])
        self.assertEqual(job.content_edit_count, 0)
        self.assertEqual(job.job_status, "OPEN")
        self.assertFalse(job.is_hidden)
        self.assertEqual(self.job.content_edit_count, 1)
        self.assertEqual(JobSkill.query.filter_by(job_id=job.job_id).count(), 1)

    def test_adjustments_work_with_and_without_content_permission(self):
        for used, has_applications in ((0, False), (1, False), (0, True), (1, True)):
            with self.subTest(used=used, has_applications=has_applications):
                self.job.content_edit_count = used
                db.session.commit()
                if has_applications:
                    self.add_application("WITHDRAWN")
                quantity = self.job.quantity + 1
                deadline = self.job.application_deadline + timedelta(days=2)
                self.post({"action": "increase_quantity", "quantity": str(quantity)})
                self.post({"action": "extend_deadline", "application_deadline": deadline.isoformat()})
                db.session.expire_all()
                self.assertEqual(self.job.quantity, quantity)
                self.assertEqual(self.job.application_deadline, deadline)
                self.assertEqual(self.job.content_edit_count, used)
                self.assertEqual(self.job.location, "Original location")

    def test_decrease_and_earlier_deadline_always_rejected(self):
        for used in (0, 1):
            with self.subTest(used=used):
                self.job.content_edit_count = used
                db.session.commit()
                deadline = self.job.application_deadline
                self.post({"action": "increase_quantity", "quantity": "2"})
                self.post({"action": "extend_deadline", "application_deadline": (deadline - timedelta(days=1)).isoformat()})
                db.session.expire_all()
                self.assertEqual(self.job.quantity, 3)
                self.assertEqual(self.job.application_deadline, deadline)
                self.assert_original(count=used)

    def test_unchanged_adjustments_do_not_consume_turn(self):
        self.post({"action": "increase_quantity", "quantity": "3"})
        self.post({"action": "extend_deadline", "application_deadline": self.job.application_deadline.isoformat()})
        self.assert_original()

    def test_all_actions_rejected_for_ineligible_jobs(self):
        deadline = self.job.application_deadline
        for status, hidden, day in (
            ("OPEN", True, deadline), ("CLOSED", False, deadline),
            ("EXPIRED", False, deadline), ("OPEN", False, date.today() - timedelta(days=1)),
            ("UNKNOWN", False, deadline)
        ):
            self.job.job_status, self.job.is_hidden, self.job.application_deadline = status, hidden, day
            db.session.commit()
            for data in (
                self.payload(), {"action": "increase_quantity", "quantity": "4"},
                {"action": "extend_deadline", "application_deadline": (deadline + timedelta(days=1)).isoformat()}
            ):
                with self.subTest(status=status, hidden=hidden, action=data["action"]):
                    self.post(data)
                    self.assert_original()
                    self.assertEqual(self.job.quantity, 3)
                    self.assertEqual(self.job.application_deadline, day)

    def test_deadline_today_is_still_open(self):
        self.job.application_deadline = date.today()
        db.session.commit()
        self.post(self.payload())
        db.session.expire_all()
        self.assertEqual(self.job.content_edit_count, 1)

    def test_invalid_values_do_not_consume_turn(self):
        for changes in (
            {"location": " "}, {"location": "x" * 256}, {"working_time": "x" * 256},
            {"min_salary": "NaN"}, {"min_salary": "Infinity"}, {"min_salary": "-1"},
            {"min_salary": "100.001"}, {"max_salary": "99999999999999"},
            {"min_salary": "30000000"}, {"max_salary": "not-money"}
        ):
            with self.subTest(changes=changes):
                self.post(self.payload(**changes))
                self.assert_original()
        for quantity in ("0", "-1", "2147483648", "3.5", "abc", ""):
            with self.subTest(quantity=quantity):
                self.post({"action": "increase_quantity", "quantity": quantity})
                self.assertEqual(self.job.quantity, 3)
                self.assert_original()
        for day in ("", "not-date", "2026-02-30", (date.today() - timedelta(days=1)).isoformat()):
            with self.subTest(deadline=day):
                original = self.job.application_deadline
                self.post({"action": "extend_deadline", "application_deadline": day})
                self.assertEqual(self.job.application_deadline, original)
                self.assert_original()

    def test_optional_content_can_be_cleared(self):
        self.post(self.payload(min_salary="", max_salary="", working_time="", benefit=""))
        db.session.expire_all()
        self.assertIsNone(self.job.min_salary)
        self.assertIsNone(self.job.max_salary)
        self.assertIsNone(self.job.working_time)
        self.assertIsNone(self.job.benefit)
        self.assertEqual(self.job.content_edit_count, 1)

    def test_extra_fields_cannot_change_protected_data(self):
        for name in ("content_edit_count", "job_title", "job_description", "job_requirement", "selected_skills", "company_id", "job_status", "is_hidden", "quantity", "application_deadline"):
            with self.subTest(field=name):
                self.post(self.payload(**{name: "0"}))
                self.assert_original()
        for action, name, value in (
            ("increase_quantity", "quantity", "4"),
            ("extend_deadline", "application_deadline", (self.job.application_deadline + timedelta(days=1)).isoformat())
        ):
            self.post({"action": action, name: value, "location": "Smuggled"})
            self.assert_original()
            self.assertEqual(self.job.quantity, 3)

    def test_invalid_missing_or_duplicate_action_fields(self):
        for data in ({}, {"action": "invalid"}, {"action": "edit_content"}):
            self.post(data)
            self.assert_original()
        duplicate = self.payload()
        duplicate["action"] = ["edit_content", "increase_quantity"]
        self.post(duplicate)
        duplicate = self.payload(location=["One", "Two"])
        self.post(duplicate)
        self.assert_original()

    def test_csrf_missing_and_invalid_blocked(self):
        for token in (None, "invalid"):
            data = self.payload()
            if token:
                data["csrf_token"] = token
            response = self.post(data, csrf_token=False)
            self.assertEqual(response.status_code, 400)
            self.assert_original()

    def test_wrong_role_and_locked_user_blocked(self):
        for role, status in (("CANDIDATE", "ACTIVE"), ("ADMIN", "ACTIVE"), ("RECRUITER", "LOCKED")):
            with self.subTest(role=role, status=status):
                self.user.role, self.user.user_status = role, status
                db.session.commit()
                self.assertEqual(self.post(self.payload()).status_code, 302)
                self.assert_original()

    def test_no_login_blocked(self):
        with self.client.session_transaction() as session:
            session.pop("user_id")
        response = self.post(self.payload())
        self.assertTrue(response.location.endswith("/auth/login"))
        self.assert_original()

    def test_other_company_and_missing_job_return_404(self):
        other = User(user_name="Other", email="other@example.invalid", password_hash="unused", role="RECRUITER")
        db.session.add(other)
        db.session.flush()
        company = Company(user_id=other.user_id, company_name="Other company")
        db.session.add(company)
        db.session.flush()
        self.job.company_id = company.company_id
        db.session.commit()
        self.assertEqual(self.post(self.payload()).status_code, 404)
        self.assert_original()
        self.assertEqual(self.client.post("/recruiter/jobs/999999/edit", data={**self.payload(), "csrf_token": self.token}).status_code, 404)

    def test_close_reopen_does_not_reset_turn(self):
        self.job.content_edit_count = 1
        db.session.commit()
        self.client.post(self.url + "/close", data={"csrf_token": self.token})
        db.session.expire_all()
        self.assertEqual(self.job.job_status, "CLOSED")
        self.assertEqual(self.job.content_edit_count, 1)
        self.client.post(self.url + "/reopen", data={"csrf_token": self.token})
        db.session.expire_all()
        self.assertEqual(self.job.job_status, "OPEN")
        self.post(self.payload())
        self.assert_original(count=1)

    def test_three_forms_have_csrf_and_separate_controls(self):
        html = self.client.get(self.url + "?edit=1").get_data(as_text=True)
        parser = FormParser(html)
        self.assertFalse(parser.nested)
        self.assertIn(WARNING, html)
        self.assertIn("còn 1 lượt", html)
        for form_id, action, fields in (
            ("editJobForm", "edit_content", {"min_salary", "max_salary", "location", "working_time", "benefit"}),
            ("increaseQuantityForm", "increase_quantity", {"quantity"}),
            ("extendDeadlineForm", "extend_deadline", {"application_deadline"})
        ):
            form = parser.forms[form_id]
            self.assertEqual(form["attrs"]["action"], self.url + "/edit")
            self.assertEqual(form["attrs"]["method"].upper(), "POST")
            self.assertEqual(form["controls"]["action"]["value"], action)
            self.assertEqual(set(form["controls"]), fields | {"action", "csrf_token"})
        self.assertEqual(parser.forms["increaseQuantityForm"]["controls"]["quantity"]["min"], "3")

    def test_locked_content_ui_keeps_adjustments(self):
        for used, applicant in ((1, False), (0, True)):
            self.job.content_edit_count = used
            db.session.commit()
            if applicant:
                self.add_application("WITHDRAWN")
            html = self.client.get(self.url + "?edit=1").get_data(as_text=True)
            forms = FormParser(html).forms
            self.assertNotIn("editJobForm", forms)
            self.assertIn("increaseQuantityForm", forms)
            self.assertIn("extendDeadlineForm", forms)
            if used:
                self.assertIn("Đã hết lượt", html)
                self.assertIn("đăng tin mới", html)

    def test_ineligible_ui_has_no_edit_forms(self):
        for status, hidden, expired in (("CLOSED", False, False), ("EXPIRED", False, False), ("OPEN", True, False), ("OPEN", False, True)):
            self.job.job_status, self.job.is_hidden = status, hidden
            if expired:
                self.job.application_deadline = date.today() - timedelta(days=1)
            db.session.commit()
            html = self.client.get(self.url + "?edit=1").get_data(as_text=True)
            forms = FormParser(html).forms
            for form_id in ("editJobForm", "increaseQuantityForm", "extendDeadlineForm"):
                self.assertNotIn(form_id, forms)

    def test_locking_reads_refresh_state_and_compile_for_mysql(self):
        # Chỉ kiểm tra truy vấn được dùng, không mô phỏng khả năng khóa của SQLite.
        statements = []
        refreshed_locks = []

        def capture(state):
            if state.is_select:
                statements.append(state.statement)
                if getattr(state.statement, "_for_update_arg", None) is not None:
                    refreshed_locks.append(getattr(state.load_options, "_populate_existing", False))

        event.listen(db.session(), "do_orm_execute", capture)
        try:
            self.post(self.payload())
        finally:
            event.remove(db.session(), "do_orm_execute", capture)
        locked = [stmt for stmt in statements if getattr(stmt, "_for_update_arg", None) is not None]
        self.assertEqual(len(locked), 2)
        sql = [str(stmt.compile(dialect=mysql.dialect())) for stmt in locked]
        self.assertTrue(all("FOR UPDATE" in statement for statement in sql))
        self.assertIn("companies", str(statements[0]))
        self.assertIn("jobs.company_id", sql[0])
        self.assertTrue(refreshed_locks[0])
        self.assertIn("applications.job_id", sql[1])
        self.assertNotIn("application_status", sql[1])

    def test_migration_chain_and_model_counter_without_running_migrations(self):
        revisions = {}
        migration = ROOT / "migrations/versions/20261021_add_job_content_edit_count.py"
        for path in migration.parent.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            values = {}
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                            values[target.id] = ast.literal_eval(node.value)
            self.assertNotIn(values["revision"], revisions)
            revisions[values["revision"]] = values["down_revision"]
        self.assertEqual(revisions["c21e4d8f6a01"], "ba1c91ecc416")
        self.assertEqual(set(revisions) - set(revisions.values()), {"c21e4d8f6a01"})
        column = Job.__table__.c.content_edit_count
        self.assertFalse(column.nullable)
        self.assertEqual(column.default.arg, 0)
        self.assertEqual(column.server_default.arg, "0")
        source = migration.read_text(encoding="utf-8")
        self.assertIn('op.add_column("jobs"', source)
        self.assertNotIn("candidate_skills", source)


if __name__ == "__main__":
    unittest.main()
