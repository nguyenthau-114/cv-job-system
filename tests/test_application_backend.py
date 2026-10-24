"""Backend Application: SQLite trong RAM, CV giả, không đọc .env/MySQL.

Chạy: .venv\Scripts\python.exe -B -m unittest tests.test_application_backend tests.test_recruiter_job_edit -v
SQLite không kiểm chứng được khóa hàng hoặc lịch chạy đồng thời của MySQL.
"""
import io
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from flask import Flask, g
from flask_wtf.csrf import generate_csrf
from sqlalchemy import MetaData, Text, event, update
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Query


safe_config = ModuleType("config")
safe_config.Config = type("TestConfig", (), {})
previous_config = sys.modules.get("config")
sys.modules["config"] = safe_config
try:
    from app.controllers.candidate_controller import candidate_bp
    from app.controllers.public_jobs_controller import public_jobs_bp
    from app.controllers.recruiter_controller import recruiter_bp
    from app.extensions import csrf, db
    from app.models.application import Application
    from app.models.candidate_skill import CandidateSkill
    from app.models.company import Company
    from app.models.cv import CV
    from app.models.job import Job
    from app.models.job_category import JobCategory
    from app.models.skill import Skill
    from app.models.user import User
    from app.services.application_service import (
        DUPLICATE_MESSAGE, submit_application, replace_application_cv, open_recruiter_application,
    )
    from app.services.cv_service import delete_cv, get_user_cvs, set_cv_visibility
finally:
    if previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = previous_config


ROOT = Path(__file__).resolve().parents[1]


class ApplicationBackendTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask("application_tests", root_path=str(ROOT / "app"))
        self.app.config.update(
            TESTING=True, SECRET_KEY="application-tests-only",
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
            SQLALCHEMY_TRACK_MODIFICATIONS=False, WTF_CSRF_ENABLED=True,
        )
        db.init_app(self.app)
        csrf.init_app(self.app)
        for bp in (candidate_bp, public_jobs_bp, recruiter_bp):
            self.app.register_blueprint(bp)
        for endpoint, path in {
            "home.home": "/", "auth.login": "/auth/login",
            "auth.register": "/auth/register", "auth.logout": "/auth/logout",
        }.items():
            self.app.add_url_rule(path, endpoint, lambda: "test")
        def fresh_token():
            # Test giữ app context qua nhiều request, không tái dùng cache token của g.
            g.pop("csrf_token", None)
            return generate_csrf()

        self.app.add_url_rule("/test-token", "test_token", fresh_token)
        context = self.app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(db.engine.dispose)
        self.addCleanup(db.session.remove)
        self.assertEqual(db.engine.url.get_backend_name(), "sqlite")
        self.assertEqual(db.engine.url.database, ":memory:")

        @event.listens_for(db.engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        metadata = MetaData()
        for table in db.metadata.sorted_tables:
            table.to_metadata(metadata)
        metadata.tables["cvs"].c.extracted_text.type = Text()
        metadata.create_all(db.engine)
        self.files = tempfile.TemporaryDirectory(prefix="jobfit-application-tests-")
        self.addCleanup(self.files.cleanup)
        self.candidate = User(
            user_name="Candidate account", email="candidate@example.invalid", phone="0900000001",
            password_hash="unused", role="CANDIDATE", email_verified=True,
        )
        self.other = User(
            user_name="Other candidate", email="other@example.invalid", phone="0900000002",
            password_hash="unused", role="CANDIDATE", email_verified=True,
        )
        self.recruiter = User(
            user_name="Recruiter", email="recruiter@example.invalid",
            password_hash="unused", role="RECRUITER", email_verified=True,
        )
        self.category = JobCategory(category_name="Synthetic category")
        db.session.add_all([self.candidate, self.other, self.recruiter, self.category])
        db.session.flush()
        self.company = Company(user_id=self.recruiter.user_id, company_name="Synthetic company")
        db.session.add(self.company)
        db.session.flush()
        self.job = Job(
            company_id=self.company.company_id, job_category_id=self.category.job_category_id,
            job_title="Synthetic job", job_description="Original JD", job_requirement="Requirements",
            experience="1 year", level="JUNIOR", quantity=1, work_mode="ONSITE",
            job_type="FULL_TIME", location="Original location", job_slug="synthetic-job",
            application_deadline=date.today() + timedelta(days=30),
        )
        db.session.add(self.job)
        self.cv = self.new_cv(self.candidate, "first.pdf")
        self.other_cv = self.new_cv(self.other, "other.pdf")
        db.session.commit()
        self.candidate_id = self.candidate.user_id
        self.job_id = self.job.job_id
        self.cv_id = self.cv.cv_id
        self.url = f"/candidate/jobs/{self.job_id}/apply"
        self.client = self.app.test_client()
        self.login(self.candidate)
        self.token = self.client.get("/test-token").get_data(as_text=True)

    def new_cv(self, user, name):
        path = Path(self.files.name) / name
        path.write_bytes(b"Synthetic CV used only for backend tests")
        cv = CV(user_id=user.user_id, file_name=name, file_path=str(path), file_type="PDF")
        db.session.add(cv)
        return cv

    def login(self, user):
        with self.client.session_transaction() as session:
            session["user_id"] = user.user_id
            session["role"] = user.role

    def payload(self, **changes):
        data = {
            "cv_id": str(self.cv_id), "contact_name": "Application name",
            "contact_email": "application@example.invalid", "contact_phone": "+84 900 000 003",
            "cover_letter": "Synthetic introduction", "csrf_token": self.token,
        }
        data.update(changes)
        return data

    def post(self, **changes):
        return self.client.post(self.url, data=self.payload(**changes))

    def existing_application(self, status="SUBMITTED"):
        application = Application(
            user_id=self.candidate_id, cv_id=self.cv_id, job_id=self.job_id,
            contact_name="Previous applicant", contact_email="previous@example.invalid",
            contact_phone="0900000001", application_status=status,
        )
        db.session.add(application)
        db.session.commit()
        return application

    def add_skill(self):
        skill = Skill(skill_name="Synthetic skill")
        db.session.add(skill)
        db.session.flush()
        saved = CandidateSkill(cv_id=self.cv_id, skill_id=skill.skill_id, extracted_name="Synthetic", source="MANUAL")
        db.session.add(saved)
        db.session.commit()
        return saved

    def test_valid_submission_snapshots_contacts_without_updating_user_cv_or_job(self):
        saved = self.add_skill()
        response = self.post(user_id=str(self.other.user_id), job_id="999999", application_status="WITHDRAWN")
        self.assertEqual(response.status_code, 201)
        application = db.session.get(Application, response.json["application_id"])
        self.assertEqual((application.user_id, application.cv_id, application.job_id), (self.candidate_id, self.cv_id, self.job_id))
        self.assertEqual(application.application_status, "SUBMITTED")
        self.assertEqual((application.contact_name, application.contact_email, application.contact_phone),
                         ("Application name", "application@example.invalid", "+84 900 000 003"))
        self.assertEqual(application.cover_letter, "Synthetic introduction")
        db.session.expire_all()
        self.assertEqual((self.candidate.user_name, self.candidate.email, self.candidate.phone),
                         ("Candidate account", "candidate@example.invalid", "0900000001"))
        self.assertEqual(self.cv.analysis_status, "PENDING")
        self.assertIsNone(self.cv.extracted_text)
        self.assertIsNone(self.cv.analyzed_at)
        self.assertEqual((saved.source, saved.extracted_name), ("MANUAL", "Synthetic"))
        self.assertEqual((self.job.quantity, self.job.content_edit_count, self.job.job_status), (1, 0, "OPEN"))

    def test_pending_cv_without_extracted_skills_is_allowed(self):
        self.assertEqual(CandidateSkill.query.count(), 0)
        self.assertEqual(self.post(cover_letter="").status_code, 201)
        self.assertIsNone(Application.query.one().cover_letter)
        self.assertEqual(self.cv.analysis_status, "PENDING")

    def test_failed_analysis_cv_is_also_allowed(self):
        self.cv.analysis_status = "FAILED"
        db.session.commit()
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.cv.analysis_status, "FAILED")

    def test_more_applications_than_quantity_are_allowed(self):
        self.assertEqual(self.post().status_code, 201)
        self.login(self.other)
        self.assertEqual(self.post(cv_id=str(self.other_cv.cv_id)).status_code, 201)
        self.assertEqual(Application.query.count(), 2)
        self.assertEqual(self.job.quantity, 1)

    def test_locked_wrong_role_and_forged_session_role_are_blocked(self):
        for role, status in (("CANDIDATE", "LOCKED"), ("RECRUITER", "ACTIVE"), ("ADMIN", "ACTIVE")):
            with self.subTest(role=role, status=status):
                self.candidate.role, self.candidate.user_status = role, status
                db.session.commit()
                self.login(self.candidate)
                self.token = self.client.get("/test-token").get_data(as_text=True)
                with self.client.session_transaction() as session:
                    session["role"] = "CANDIDATE"
                self.assertEqual(self.post().status_code, 302)
                self.assertEqual(Application.query.count(), 0)

    def test_no_login_or_deleted_user_is_blocked(self):
        for user_id in (None, 999999):
            with self.subTest(user_id=user_id):
                # Lấy token mới vì middleware có thể xóa session không hợp lệ.
                self.token = self.client.get("/test-token").get_data(as_text=True)
                with self.client.session_transaction() as session:
                    session.pop("user_id", None)
                    if user_id is not None:
                        session["user_id"] = user_id
                self.assertEqual(self.post().status_code, 302)
                self.assertEqual(Application.query.count(), 0)

    def test_service_itself_checks_role_and_account_status(self):
        for role, status in (("RECRUITER", "ACTIVE"), ("CANDIDATE", "LOCKED")):
            self.candidate.role, self.candidate.user_status = role, status
            db.session.commit()
            application, errors = submit_application(self.candidate_id, self.job_id, self.payload())
            self.assertIsNone(application)
            self.assertIn("account", errors)
        self.assertEqual(Application.query.count(), 0)

    def test_closed_expired_hidden_and_unknown_jobs_are_blocked(self):
        for status, hidden, deadline in (
            ("CLOSED", False, date.today()), ("EXPIRED", False, date.today()),
            ("OPEN", True, date.today()), ("HIDDEN", False, date.today()),
            ("OPEN", False, date.today() - timedelta(days=1)),
        ):
            with self.subTest(status=status, hidden=hidden, deadline=deadline):
                self.job.job_status, self.job.is_hidden, self.job.application_deadline = status, hidden, deadline
                db.session.commit()
                response = self.post()
                self.assertEqual(response.status_code, 400)
                self.assertIn("job", response.json["errors"])
                self.assertEqual(Application.query.count(), 0)

    def test_missing_job_is_blocked(self):
        response = self.client.post("/candidate/jobs/999999/apply", data=self.payload())
        self.assertEqual(response.status_code, 400)
        self.assertIn("job", response.json["errors"])

    def test_deadline_today_accepts_application(self):
        self.job.application_deadline = date.today()
        db.session.commit()
        self.assertEqual(self.post().status_code, 201)

    def test_cv_ownership_missing_and_invalid_ids_are_blocked(self):
        for cv_id in (str(self.other_cv.cv_id), "999999", "0", "-1", "1.5", "2147483648", "", "abc"):
            with self.subTest(cv_id=cv_id):
                response = self.post(cv_id=cv_id)
                self.assertEqual(response.status_code, 400)
                self.assertIn("cv_id", response.json["errors"])
                self.assertEqual(response.json["manage_cvs_url"], "/candidate/cvs")
                self.assertEqual(Application.query.count(), 0)

    def test_missing_cv_guides_to_management(self):
        db.session.delete(self.cv)
        db.session.commit()
        response = self.post(cv_id="")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Quản lý CV", response.json["errors"]["cv_id"])

    def test_upload_is_rejected_without_saving_file_or_cv(self):
        data = self.payload()
        data["cv_file"] = (io.BytesIO(b"synthetic upload"), "new.pdf")
        before = sorted(Path(self.files.name).iterdir())
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CV.query.count(), 2)
        self.assertEqual(sorted(Path(self.files.name).iterdir()), before)
        self.assertEqual(Application.query.count(), 0)

    def test_required_contact_lengths_formats_and_duplicate_fields(self):
        for field, value in (
            ("contact_name", " "), ("contact_email", ""), ("contact_phone", ""),
            ("contact_name", "x" * 101), ("contact_email", "x" * 256),
            ("contact_phone", "1" * 21), ("contact_email", "not-an-email"),
            ("contact_phone", "not-a-phone"), ("cover_letter", "x" * 5001),
            ("contact_name", "bad\x00name"), ("cover_letter", "bad\x00text"),
            ("cv_id", [str(self.cv_id), str(self.other_cv.cv_id)]),
            ("contact_email", ["one@example.invalid", "two@example.invalid"]),
        ):
            with self.subTest(field=field):
                response = self.post(**{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.json["errors"])
                self.assertEqual(Application.query.count(), 0)

    def test_maximum_contact_and_cover_lengths_are_accepted(self):
        response = self.post(contact_name="x" * 100, contact_email="a" * 243 + "@example.com",
                             contact_phone="+" + "1" * 19, cover_letter="x" * 5000)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(Application.query.one().cover_letter), 5000)

    def test_duplicate_and_withdrawn_applications_remain_blocked_with_another_cv(self):
        application = self.existing_application()
        cv = self.new_cv(self.candidate, "second.pdf")
        db.session.commit()
        for status in ("SUBMITTED", "WITHDRAWN"):
            application.application_status = status
            db.session.commit()
            response = self.post(cv_id=str(cv.cv_id))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json["errors"]["application"], DUPLICATE_MESSAGE)
            self.assertEqual(Application.query.count(), 1)
            self.assertEqual(application.cv_id, self.cv_id)

    def test_unique_constraint_catches_a_missed_duplicate_precheck(self):
        original = self.existing_application("WITHDRAWN")
        first = Query.first

        def miss_precheck(query):
            if query.column_descriptions[0].get("entity") is Application and query._for_update_arg is not None:
                return None
            return first(query)

        # Bỏ qua đúng bước precheck để DB thật của test phát sinh IntegrityError.
        with patch.object(Query, "first", miss_precheck):
            response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["errors"]["application"], DUPLICATE_MESSAGE)
        self.assertEqual(Application.query.count(), 1)
        self.assertEqual(Application.query.one().application_id, original.application_id)
        self.assertTrue(db.session.is_active)

    def test_nonduplicate_integrity_error_is_safe_and_session_can_be_reused(self):
        with patch.object(db.session, "commit", side_effect=IntegrityError("test", {}, Exception("synthetic"))):
            response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("đã ứng tuyển", response.json["errors"]["application"])
        self.assertEqual(Application.query.count(), 0)
        self.assertEqual(self.post().status_code, 201)

    def test_commit_failure_after_flush_rolls_back_application(self):
        def fail_commit():
            db.session.flush()
            raise SQLAlchemyError("synthetic commit failure")

        with patch.object(db.session, "commit", side_effect=fail_commit), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.post()
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Application.query.count(), 0)
        self.assertTrue(Path(self.cv.file_path).exists())
        self.assertEqual(self.job.quantity, 1)

    def test_missing_invalid_csrf_and_get_cannot_submit(self):
        for token in ("", "invalid"):
            self.assertEqual(self.post(csrf_token=token).status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(Application.query.count(), 0)

    def test_stale_user_and_job_state_is_refreshed_before_submission(self):
        real_session = db.session()
        previous = real_session.expire_on_commit
        real_session.expire_on_commit = False
        try:
            db.session.execute(update(User).where(User.user_id == self.candidate_id).values(user_status="LOCKED").execution_options(synchronize_session=False))
            db.session.commit()
            self.assertEqual(self.candidate.user_status, "ACTIVE")
            application, errors = submit_application(self.candidate_id, self.job_id, self.payload())
            self.assertIsNone(application)
            self.assertIn("account", errors)
            self.candidate.user_status = "ACTIVE"
            db.session.commit()
            self.assertEqual(self.job.job_status, "OPEN")
            db.session.execute(update(Job).where(Job.job_id == self.job_id).values(job_status="CLOSED").execution_options(synchronize_session=False))
            db.session.commit()
            self.assertEqual(self.job.job_status, "OPEN")
            application, errors = submit_application(self.candidate_id, self.job_id, self.payload())
            self.assertIsNone(application)
            self.assertIn("job", errors)
        finally:
            real_session.expire_on_commit = previous

    def test_linked_cv_cannot_be_deleted_even_when_withdrawn(self):
        saved = self.add_skill()
        application = self.existing_application()
        for status in ("SUBMITTED", "WITHDRAWN"):
            application.application_status = status
            db.session.commit()
            response = self.client.post(f"/candidate/cvs/{self.cv_id}/delete", data={"csrf_token": self.token})
            self.assertEqual(response.status_code, 302)
            self.assertIsNotNone(db.session.get(CV, self.cv_id))
            self.assertIsNotNone(db.session.get(CandidateSkill, saved.candidate_skill_id))
            self.assertEqual(Application.query.count(), 1)
            self.assertTrue(Path(self.cv.file_path).exists())
            with self.client.session_transaction() as session:
                self.assertIn("đã được sử dụng", session["_flashes"][-1][1])

    def test_unlinked_cv_with_skills_can_be_deleted_without_affecting_other_cv(self):
        self.add_skill()
        path = self.cv.file_path
        success, message = delete_cv(self.candidate_id, self.cv_id)
        self.assertTrue(success, message)
        self.assertIsNone(db.session.get(CV, self.cv_id))
        self.assertEqual(CandidateSkill.query.count(), 0)
        self.assertFalse(Path(path).exists())
        self.assertIsNotNone(db.session.get(CV, self.other_cv.cv_id))
        self.assertTrue(Path(self.other_cv.file_path).exists())

    def test_delete_other_candidates_cv_or_without_csrf_is_blocked(self):
        success, _ = delete_cv(self.candidate_id, self.other_cv.cv_id)
        self.assertFalse(success)
        response = self.client.post(f"/candidate/cvs/{self.cv_id}/delete")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CV.query.count(), 2)
        self.assertTrue(Path(self.other_cv.file_path).exists())

    def test_fk_protects_cv_and_skills_when_reference_precheck_misses(self):
        saved = self.add_skill()
        self.existing_application()
        first = Query.first

        def miss_precheck(query):
            if query.column_descriptions[0].get("entity") is Application and query._for_update_arg is not None:
                return None
            return first(query)

        with patch.object(Query, "first", miss_precheck):
            success, _ = delete_cv(self.candidate_id, self.cv_id)
        self.assertFalse(success)
        self.assertIsNotNone(db.session.get(CV, self.cv_id))
        self.assertIsNotNone(db.session.get(CandidateSkill, saved.candidate_skill_id))
        self.assertEqual(Application.query.count(), 1)
        self.assertTrue(Path(self.cv.file_path).exists())

    def test_application_locks_recruiter_content_but_keeps_adjustments(self):
        self.assertEqual(self.post().status_code, 201)
        application = Application.query.one()
        self.login(self.recruiter)
        edit_url = f"/recruiter/jobs/{self.job_id}/edit"
        for status in ("SUBMITTED", "WITHDRAWN"):
            application.application_status = status
            db.session.commit()
            self.client.post(edit_url, data={
                "csrf_token": self.token, "action": "edit_content", "location": "Forbidden change",
                "min_salary": "", "max_salary": "", "working_time": "", "benefit": "",
            })
            quantity = self.job.quantity + 1
            deadline = self.job.application_deadline + timedelta(days=1)
            self.client.post(edit_url, data={"csrf_token": self.token, "action": "increase_quantity", "quantity": str(quantity)})
            self.client.post(edit_url, data={"csrf_token": self.token, "action": "extend_deadline", "application_deadline": deadline.isoformat()})
            db.session.expire_all()
            self.assertEqual(self.job.location, "Original location")
            self.assertEqual(self.job.content_edit_count, 0)
            self.assertEqual(self.job.quantity, quantity)
            self.assertEqual(self.job.application_deadline, deadline)

    def test_locking_reads_compile_for_mysql_and_refresh_parent_state(self):
        locked = []

        def capture(state):
            if state.is_select and getattr(state.statement, "_for_update_arg", None) is not None:
                locked.append((state.statement, getattr(state.load_options, "_populate_existing", False)))

        event.listen(db.session(), "do_orm_execute", capture)
        try:
            self.assertEqual(self.post().status_code, 201)
        finally:
            event.remove(db.session(), "do_orm_execute", capture)
        self.assertEqual(len(locked), 4)
        for statement, _ in locked:
            self.assertIn("FOR UPDATE", str(statement.compile(dialect=mysql.dialect())))
        self.assertTrue(all(refresh for _, refresh in locked[:3]))

    def test_existing_job_pages_and_candidate_cv_page_still_render(self):
        for url in ("/jobs", f"/jobs/{self.job_id}", "/candidate/cvs"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)


    def visibility(self, cv_id=None, **changes):
        data = {"csrf_token": self.token, "is_hidden": "1"}
        data.update(changes)
        return self.client.post(f"/candidate/cvs/{cv_id or self.cv_id}/visibility", data=data)

    def replacement(self, application_id, selected_cv_id, **changes):
        data = {"csrf_token": self.token, "cv_id": str(selected_cv_id)}
        data.update(changes)
        return self.client.post(f"/candidate/applications/{application_id}/cv", data=data)

    def recruiter_open(self, application_id, with_cv=False, **changes):
        data = {"csrf_token": self.token}
        data.update(changes)
        suffix = "cv" if with_cv else "open"
        return self.client.post(f"/recruiter/applications/{application_id}/{suffix}", data=data)

    def application_snapshot(self, application):
        db.session.refresh(application)
        return {column.name: getattr(application, column.name) for column in Application.__table__.columns}

    def additional_application(self, status, cv_id=None):
        suffix = Job.query.count() + 1
        job = Job(
            company_id=self.company.company_id, job_category_id=self.category.job_category_id,
            job_title="Additional synthetic job", job_description="JD", job_requirement="Requirements",
            experience="1 year", level="JUNIOR", quantity=1, work_mode="ONSITE", job_type="FULL_TIME",
            location="Synthetic", job_slug=f"additional-synthetic-job-{suffix}", application_deadline=date.today(),
        )
        db.session.add(job)
        db.session.flush()
        application = Application(
            user_id=self.candidate_id, cv_id=self.cv_id if cv_id is None else cv_id, job_id=job.job_id,
            contact_name="Additional applicant", contact_email="additional@example.invalid",
            contact_phone="0900000001", application_status=status,
        )
        db.session.add(application)
        db.session.commit()
        return application

    def test_hiding_blocks_every_unfinished_status_without_changing_application_or_skills(self):
        skill = self.add_skill()
        application = self.existing_application()
        for status in ("SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW"):
            with self.subTest(status=status):
                application.application_status = status
                db.session.commit()
                before = self.application_snapshot(application)
                response = self.visibility()
                self.assertEqual(response.status_code, 400)
                self.assertIn("chưa kết thúc", response.json["errors"]["cv"])
                self.assertFalse(self.cv.is_hidden)
                self.assertEqual(self.application_snapshot(application), before)
                self.assertEqual((skill.source, self.cv.analysis_status), ("MANUAL", "PENDING"))
                self.assertTrue(Path(self.cv.file_path).exists())

    def test_hiding_rejects_unknown_empty_and_nonexact_terminal_statuses(self):
        application = self.existing_application()
        for status in ("", "UNKNOWN", "ACCEPTED", "rejected", "Rejected", "withdrawn", "REJECTED ", " WITHDRAWN", "WITHDRAWN\n"):
            with self.subTest(status=repr(status)):
                application.application_status = status
                db.session.commit()
                before = self.application_snapshot(application)
                self.assertEqual(self.visibility().status_code, 400)
                self.assertFalse(self.cv.is_hidden)
                self.assertEqual(self.application_snapshot(application), before)

    def test_hiding_rejects_null_status_returned_by_locked_query(self):
        application = self.existing_application("WITHDRAWN")
        before = self.application_snapshot(application)
        original_all, queries = Query.all, []

        def legacy_null_result(query):
            rows = original_all(query)
            if query._for_update_arg is not None and query.column_descriptions[0]["name"] == "application_status":
                queries.append(query)
                # Model hiện tại là NOT NULL; mô phỏng kết quả DB cũ lỗi, không đổi schema test.
                self.assertEqual(len(rows), 1)
                return [SimpleNamespace(application_status=None)]
            return rows

        with patch.object(Query, "all", legacy_null_result):
            self.assertEqual(self.visibility().status_code, 400)
        self.assertEqual(len(queries), 1)
        self.assertFalse(self.cv.is_hidden)
        self.assertEqual(self.application_snapshot(application), before)

    def test_hiding_checks_all_references_including_a_later_unfinished_application(self):
        first = self.existing_application("REJECTED")
        second = self.additional_application("WITHDRAWN")
        self.assertEqual(self.visibility().status_code, 200)
        self.assertEqual(self.visibility(is_hidden="0").status_code, 200)
        third = self.additional_application("INTERVIEW")
        before = [self.application_snapshot(application) for application in (first, second, third)]
        self.assertEqual(self.visibility().status_code, 400)
        self.assertFalse(self.cv.is_hidden)
        self.assertEqual([self.application_snapshot(application) for application in (first, second, third)], before)
        third.application_status = "WITHDRAWN"
        db.session.commit()
        self.assertEqual(self.visibility().status_code, 200)

    def test_applications_for_another_cv_do_not_block_hiding_unreferenced_cv(self):
        new_cv = self.new_cv(self.candidate, "linked.pdf")
        db.session.commit()
        application = self.additional_application("SUBMITTED", cv_id=new_cv.cv_id)
        before = self.application_snapshot(application)
        self.assertEqual(self.visibility().status_code, 200)
        self.assertTrue(self.cv.is_hidden)
        self.assertFalse(new_cv.is_hidden)
        self.assertEqual(self.application_snapshot(application), before)

    def test_already_hidden_cv_still_requires_all_applications_to_be_terminal(self):
        application = self.existing_application()
        for status in ("SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW", "UNKNOWN", ""):
            with self.subTest(status=status):
                application.application_status = status
                self.cv.is_hidden = True
                db.session.commit()
                before = self.application_snapshot(application)
                with patch.object(db.session, "commit") as commit:
                    self.assertEqual(self.visibility().status_code, 400)
                commit.assert_not_called()
                self.assertTrue(self.cv.is_hidden)
                self.assertEqual(self.application_snapshot(application), before)

    def test_unhiding_is_allowed_with_any_referenced_application_status(self):
        application = self.existing_application()
        for status in ("SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW", "REJECTED", "WITHDRAWN", "UNKNOWN", ""):
            with self.subTest(status=status):
                application.application_status = status
                self.cv.is_hidden = True
                db.session.commit()
                before = self.application_snapshot(application)
                self.assertEqual(self.visibility(is_hidden="0").status_code, 200)
                self.assertFalse(self.cv.is_hidden)
                self.assertEqual(self.application_snapshot(application), before)

    def test_hiding_reads_current_application_status_despite_stale_identity_map(self):
        application = self.existing_application("REJECTED")
        real_session = db.session()
        previous = real_session.expire_on_commit
        real_session.expire_on_commit = False
        try:
            db.session.execute(update(Application).where(Application.application_id == application.application_id).values(application_status="SUBMITTED").execution_options(synchronize_session=False))
            db.session.commit()
            self.assertEqual(application.application_status, "REJECTED")
            success, _ = set_cv_visibility(self.candidate_id, self.cv_id, True)
            self.assertFalse(success)
            self.assertFalse(self.cv.is_hidden)
            self.assertEqual(application.application_status, "SUBMITTED")
        finally:
            real_session.expire_on_commit = previous

    def test_hiding_query_failure_rolls_back_without_changing_cv_or_application(self):
        application = self.existing_application("WITHDRAWN")
        before = self.application_snapshot(application)
        original_all = Query.all

        def fail_locked_application_read(query):
            if query._for_update_arg is not None and query.column_descriptions[0]["name"] == "application_status":
                raise SQLAlchemyError("synthetic locking read failure")
            return original_all(query)

        with patch.object(Query, "all", fail_locked_application_read), self.assertLogs(self.app.logger, level="ERROR"):
            self.assertEqual(self.visibility().status_code, 400)
        self.assertFalse(self.cv.is_hidden)
        self.assertEqual(self.application_snapshot(application), before)
        self.assertTrue(db.session.is_active)
        self.assertEqual(self.visibility().status_code, 200)

    def test_unhiding_commit_failure_after_flush_preserves_hidden_cv_and_application(self):
        application = self.existing_application()
        self.cv.is_hidden = True
        db.session.commit()
        before = self.application_snapshot(application)

        def fail_commit():
            db.session.flush()
            raise SQLAlchemyError("synthetic commit failure")

        with patch.object(db.session, "commit", side_effect=fail_commit), self.assertLogs(self.app.logger, level="ERROR"):
            self.assertEqual(self.visibility(is_hidden="0").status_code, 400)
        self.assertTrue(self.cv.is_hidden)
        self.assertEqual(self.application_snapshot(application), before)
        self.assertEqual(self.visibility(is_hidden="0").status_code, 200)

    def test_submitting_before_hiding_blocks_hide_and_preserves_submission(self):
        self.assertEqual(self.post().status_code, 201)
        application = Application.query.one()
        before = self.application_snapshot(application)
        self.assertEqual(self.visibility().status_code, 400)
        self.assertFalse(self.cv.is_hidden)
        self.assertEqual(self.application_snapshot(application), before)

    def test_replacing_away_from_cv_allows_hiding_it_when_no_reference_remains(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        self.assertEqual(self.visibility().status_code, 400)
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
        before = self.application_snapshot(application)
        self.assertEqual(self.visibility().status_code, 200)
        self.assertEqual(self.visibility(cv_id=new_cv.cv_id).status_code, 400)
        self.assertEqual(self.application_snapshot(application), before)
        self.assertTrue(self.cv.is_hidden)
        self.assertFalse(new_cv.is_hidden)

    def test_recruiter_can_open_cv_hidden_after_all_applications_end_but_delete_stays_blocked(self):
        application = self.existing_application("REJECTED")
        for status in ("REJECTED", "WITHDRAWN"):
            with self.subTest(status=status):
                application.application_status = status
                db.session.commit()
                self.login(self.candidate)
                self.assertEqual(self.visibility().status_code, 200)
                before = self.application_snapshot(application)
                self.assertFalse(delete_cv(self.candidate_id, self.cv_id)[0])
                self.login(self.recruiter)
                detail = self.recruiter_open(application.application_id)
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json["application"]["application_status"], status)
                response = self.recruiter_open(application.application_id, with_cv=True)
                try:
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.data, b"Synthetic CV used only for backend tests")
                finally:
                    response.close()
                self.assertEqual(self.application_snapshot(application), before)
                self.assertTrue(self.cv.is_hidden)
                self.assertIsNotNone(db.session.get(CV, self.cv_id))

    def test_visibility_allows_only_terminal_linked_cv_and_preserves_application_and_skills(self):
        skill = self.add_skill()
        application = self.existing_application()
        for status in ("REJECTED", "WITHDRAWN"):
            application.application_status = status
            db.session.commit()
            before = self.application_snapshot(application)
            for hidden in ("1", "0"):
                with self.subTest(status=status, hidden=hidden):
                    response = self.visibility(is_hidden=hidden)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json["is_hidden"], hidden == "1")
                    self.assertEqual(self.cv.is_hidden, hidden == "1")
                    self.assertEqual(self.application_snapshot(application), before)
                    self.assertEqual(skill.source, "MANUAL")
                    self.assertEqual(self.cv.analysis_status, "PENDING")

    def test_hidden_cvs_remain_in_own_management_and_can_be_viewed(self):
        self.assertEqual(self.visibility().status_code, 200)
        self.assertIn(self.cv_id, [cv.cv_id for cv in get_user_cvs(self.candidate_id)])
        response = self.client.get("/candidate/cvs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"first.pdf", response.data)
        response = self.client.get(f"/candidate/cvs/{self.cv_id}/view")
        try:
            self.assertEqual(response.status_code, 200)
        finally:
            response.close()

    def test_visibility_ownership_and_missing_cv_are_rejected(self):
        for cv_id in (self.other_cv.cv_id, 999999):
            self.assertEqual(self.visibility(cv_id=cv_id).status_code, 400)
        self.assertFalse(self.other_cv.is_hidden)
        self.assertFalse(self.cv.is_hidden)

    def test_visibility_is_idempotent_and_validates_exact_boolean_input(self):
        self.assertEqual(self.visibility().status_code, 200)
        with patch.object(db.session, "commit") as commit:
            self.assertEqual(self.visibility().status_code, 200)
        commit.assert_not_called()
        for value in ("", "true", "False", "2", ["1", "0"]):
            self.assertEqual(self.visibility(is_hidden=value).status_code, 400)
        self.assertEqual(self.visibility(application_status="SUBMITTED").status_code, 400)
        self.assertFalse(set_cv_visibility(self.candidate_id, self.cv_id, "1")[0])
        self.assertTrue(self.cv.is_hidden)

    def test_hidden_cv_is_rejected_at_submission_without_application_changes(self):
        self.assertEqual(self.visibility().status_code, 200)
        self.assertEqual(self.post().status_code, 400)
        self.assertEqual(Application.query.count(), 0)
        self.assertEqual(self.visibility(is_hidden="0").status_code, 200)
        self.assertEqual(self.post().status_code, 201)

    def test_stale_cached_visibility_is_refreshed_before_submission(self):
        real_session = db.session()
        previous = real_session.expire_on_commit
        real_session.expire_on_commit = False
        try:
            self.assertFalse(self.cv.is_hidden)
            db.session.execute(update(CV).where(CV.cv_id == self.cv_id).values(is_hidden=True).execution_options(synchronize_session=False))
            db.session.commit()
            self.assertFalse(self.cv.is_hidden)
            result, errors = submit_application(self.candidate_id, self.job_id, self.payload())
            self.assertIsNone(result)
            self.assertIn("cv_id", errors)
        finally:
            real_session.expire_on_commit = previous

    def test_replace_only_updates_cv_id_preserving_contacts_time_status_and_skills(self):
        skill = self.add_skill()
        application = self.existing_application()
        application.cover_letter = "Original cover letter"
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        before = self.application_snapshot(application)
        response = self.replacement(application.application_id, new_cv.cv_id)
        self.assertEqual(response.status_code, 200)
        after = self.application_snapshot(application)
        before["cv_id"] = new_cv.cv_id
        self.assertEqual(after, before)
        self.assertEqual(Application.query.count(), 1)
        self.assertEqual((new_cv.analysis_status, self.cv.analysis_status), ("PENDING", "PENDING"))
        self.assertIsNone(new_cv.extracted_text)
        self.assertEqual((skill.cv_id, skill.source), (self.cv_id, "MANUAL"))
        self.assertEqual(self.candidate.user_name, "Candidate account")

    def test_replace_does_not_require_open_visible_or_unexpired_job(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        for status in ("CLOSED", "EXPIRED", "HIDDEN"):
            self.job.job_status, self.job.is_hidden = status, True
            self.job.application_deadline = date.today() - timedelta(days=1)
            db.session.commit()
            target = new_cv.cv_id if application.cv_id == self.cv_id else self.cv_id
            self.assertEqual(self.replacement(application.application_id, target).status_code, 200)

    def test_replace_rejects_every_status_except_exact_submitted(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        for status in ("VIEWED", "CONSIDERING", "INTERVIEW", "REJECTED", "WITHDRAWN", "UNKNOWN", "submitted"):
            with self.subTest(status=status):
                application.application_status = status
                db.session.commit()
                response = self.replacement(application.application_id, new_cv.cv_id)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(application.cv_id, self.cv_id)
                self.assertEqual(application.application_status, status)

    def test_replace_rejects_foreign_hidden_missing_or_invalid_cv(self):
        application = self.existing_application()
        hidden_cv = self.new_cv(self.candidate, "hidden.pdf")
        hidden_cv.is_hidden = True
        db.session.commit()
        for cv_id in (self.other_cv.cv_id, hidden_cv.cv_id, 999999, "0", "-1", "1.1", "2147483648", "abc", ""):
            self.assertEqual(self.replacement(application.application_id, cv_id).status_code, 400)
            self.assertEqual(application.cv_id, self.cv_id)
        for cv_id in (True, 1.5, [], {}, None):
            self.assertIn("cv_id", replace_application_cv(self.candidate_id, application.application_id, cv_id)[1])

    def test_replace_rejects_foreign_or_missing_application(self):
        application = self.existing_application()
        self.login(self.other)
        for application_id in (application.application_id, 999999):
            response = self.replacement(application_id, self.other_cv.cv_id)
            self.assertEqual(response.status_code, 404)
        self.assertEqual(application.cv_id, self.cv_id)

    def test_replace_same_visible_cv_is_noop_without_commit(self):
        application = self.existing_application()
        before = self.application_snapshot(application)
        with patch.object(db.session, "commit") as commit:
            self.assertEqual(self.replacement(application.application_id, self.cv_id).status_code, 200)
        commit.assert_not_called()
        self.assertEqual(self.application_snapshot(application), before)

    def test_replace_rejects_uploads_duplicate_fields_and_snapshot_mutation(self):
        application = self.existing_application()
        for changes in (
            {"application_status": "SUBMITTED"}, {"contact_name": "Forged"}, {"user_id": str(self.other.user_id)},
            {"cv_id": [str(self.cv_id), str(self.other_cv.cv_id)]},
            {"file": (io.BytesIO(b"synthetic"), "upload.pdf")},
        ):
            self.assertEqual(self.replacement(application.application_id, self.cv_id, **changes).status_code, 400)
        self.assertEqual(application.contact_name, "Previous applicant")

    def test_unreferenced_old_cv_can_be_deleted_after_replacement(self):
        self.add_skill()
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        old_path = self.cv.file_path
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
        success, message = delete_cv(self.candidate_id, self.cv_id)
        self.assertTrue(success, message)
        self.assertFalse(Path(old_path).exists())
        self.assertIsNone(db.session.get(CV, self.cv_id))
        self.assertEqual(application.cv_id, new_cv.cv_id)
        self.assertEqual(Application.query.count(), 1)

    def test_old_cv_still_referenced_by_another_application_cannot_be_deleted(self):
        application = self.existing_application()
        another_job = Job(
            company_id=self.company.company_id, job_category_id=self.category.job_category_id,
            job_title="Second synthetic job", job_description="JD", job_requirement="Requirements",
            experience="1 year", level="JUNIOR", quantity=1, work_mode="ONSITE", job_type="FULL_TIME",
            location="Synthetic", job_slug="second-synthetic-job", application_deadline=date.today(),
        )
        db.session.add(another_job)
        db.session.flush()
        other_application = Application(
            user_id=self.candidate_id, cv_id=self.cv_id, job_id=another_job.job_id,
            contact_name="Other application", contact_email="other@example.invalid", contact_phone="0900000001",
            application_status="WITHDRAWN",
        )
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.add(other_application)
        db.session.commit()
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
        self.assertFalse(delete_cv(self.candidate_id, self.cv_id)[0])
        self.assertIsNotNone(db.session.get(CV, self.cv_id))
        self.assertEqual(other_application.cv_id, self.cv_id)

    def test_recruiter_open_marks_submitted_viewed_and_preserves_snapshot(self):
        application = self.existing_application()
        before = self.application_snapshot(application)
        self.login(self.recruiter)
        response = self.recruiter_open(application.application_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["application"]["contact_email"], before["contact_email"])
        self.assertEqual(response.json["application"]["application_status"], "VIEWED")
        before["application_status"] = "VIEWED"
        self.assertEqual(self.application_snapshot(application), before)
        self.assertEqual(response.headers["Cache-Control"], "private, no-store")

    def test_recruiter_can_open_submitted_hidden_cv_and_mark_viewed(self):
        application = self.existing_application()
        # Dữ liệu cũ có thể đã ẩn trước khi áp dụng quy tắc mới, Recruiter vẫn được xem.
        self.cv.is_hidden = True
        db.session.commit()
        self.login(self.recruiter)
        response = self.recruiter_open(application.application_id, with_cv=True)
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"Synthetic CV used only for backend tests")
            self.assertEqual(response.mimetype, "application/pdf")
            self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        finally:
            response.close()
        self.assertEqual(application.application_status, "VIEWED")
        self.assertTrue(self.cv.is_hidden)

    def test_recruiter_open_never_overwrites_viewed_processing_withdrawn_or_unknown_status(self):
        application = self.existing_application()
        self.login(self.recruiter)
        for status in ("VIEWED", "CONSIDERING", "INTERVIEW", "REJECTED", "WITHDRAWN", "UNKNOWN"):
            application.application_status = status
            db.session.commit()
            for with_cv in (False, True):
                response = self.recruiter_open(application.application_id, with_cv=with_cv)
                try:
                    self.assertEqual(response.status_code, 200)
                finally:
                    response.close()
                self.assertEqual(application.application_status, status)

    def test_wrong_company_and_missing_application_cannot_be_opened_or_marked(self):
        application = self.existing_application()
        stranger = User(user_name="Other recruiter", email="stranger@example.invalid", password_hash="unused", role="RECRUITER")
        db.session.add(stranger)
        db.session.flush()
        db.session.add(Company(user_id=stranger.user_id, company_name="Other company"))
        db.session.commit()
        self.login(stranger)
        with patch("app.services.application_service.open", create=True) as open_file:
            for application_id in (application.application_id, 999999):
                for with_cv in (False, True):
                    self.assertEqual(self.recruiter_open(application_id, with_cv=with_cv).status_code, 404)
        open_file.assert_not_called()
        self.assertEqual(application.application_status, "SUBMITTED")

    def test_new_routes_require_role_active_user_login_and_csrf(self):
        application = self.existing_application()
        candidate_urls = (f"/candidate/cvs/{self.cv_id}/visibility", f"/candidate/applications/{application.application_id}/cv")
        recruiter_urls = tuple(f"/recruiter/applications/{application.application_id}/{suffix}" for suffix in ("open", "cv"))
        for user, urls, wrong_role in ((self.candidate, candidate_urls, "RECRUITER"), (self.recruiter, recruiter_urls, "CANDIDATE")):
            original_role = user.role
            for status, role in (("LOCKED", original_role), ("ACTIVE", wrong_role)):
                user.user_status, user.role = status, role
                db.session.commit()
                for url in urls:
                    # Tài khoản bị khóa làm middleware xóa cả session và CSRF token.
                    self.login(user)
                    self.token = self.client.get("/test-token").get_data(as_text=True)
                    self.assertEqual(self.client.post(url, data={"csrf_token": self.token}).status_code, 302)
            user.user_status, user.role = "ACTIVE", original_role
            db.session.commit()
        for url in candidate_urls + recruiter_urls:
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.post(url).status_code, 400)
            self.assertEqual(self.client.post(url, data={"csrf_token": "invalid"}).status_code, 400)
        self.assertEqual(application.application_status, "SUBMITTED")
        self.assertFalse(self.cv.is_hidden)

    def test_new_routes_reject_anonymous_requests_even_with_valid_csrf(self):
        application = self.existing_application()
        urls = (
            f"/candidate/cvs/{self.cv_id}/visibility",
            f"/candidate/applications/{application.application_id}/cv",
            f"/recruiter/applications/{application.application_id}/open",
            f"/recruiter/applications/{application.application_id}/cv",
        )
        for url in urls:
            with self.client.session_transaction() as session:
                session.clear()
            token = self.client.get("/test-token").get_data(as_text=True)
            self.assertEqual(self.client.post(url, data={"csrf_token": token}).status_code, 302)
        self.assertEqual(application.application_status, "SUBMITTED")

    def test_replacement_refreshes_cached_application_status_and_cv_visibility(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        real_session = db.session()
        previous = real_session.expire_on_commit
        real_session.expire_on_commit = False
        try:
            self.assertEqual(application.application_status, "SUBMITTED")
            db.session.execute(update(Application).where(Application.application_id == application.application_id).values(application_status="VIEWED").execution_options(synchronize_session=False))
            db.session.commit()
            self.assertEqual(application.application_status, "SUBMITTED")
            result, errors = replace_application_cv(self.candidate_id, application.application_id, new_cv.cv_id)
            self.assertIsNone(result)
            self.assertIn("state", errors)
            application.application_status = "SUBMITTED"
            db.session.commit()
            self.assertFalse(new_cv.is_hidden)
            db.session.execute(update(CV).where(CV.cv_id == new_cv.cv_id).values(is_hidden=True).execution_options(synchronize_session=False))
            db.session.commit()
            self.assertFalse(new_cv.is_hidden)
            result, errors = replace_application_cv(self.candidate_id, application.application_id, new_cv.cv_id)
            self.assertIsNone(result)
            self.assertIn("cv_id", errors)
            self.assertEqual(application.cv_id, self.cv_id)
        finally:
            real_session.expire_on_commit = previous

    def test_new_services_recheck_active_role_independently_of_middleware(self):
        application = self.existing_application()
        for role, status in (("RECRUITER", "ACTIVE"), ("CANDIDATE", "LOCKED")):
            self.candidate.role, self.candidate.user_status = role, status
            db.session.commit()
            self.assertFalse(set_cv_visibility(self.candidate_id, self.cv_id, True)[0])
            self.assertIn("account", replace_application_cv(self.candidate_id, application.application_id, self.cv_id)[1])
        for role, status in (("CANDIDATE", "ACTIVE"), ("RECRUITER", "LOCKED")):
            self.recruiter.role, self.recruiter.user_status = role, status
            db.session.commit()
            self.assertIn("account", open_recruiter_application(self.recruiter.user_id, application.application_id)[1])

    def test_recruiter_routes_reject_arbitrary_cv_and_status_input(self):
        application = self.existing_application()
        self.login(self.recruiter)
        for with_cv in (False, True):
            for changes in ({"cv_id": str(self.other_cv.cv_id)}, {"application_status": "SUBMITTED"}, {"file": (io.BytesIO(b"synthetic"), "new.pdf")}):
                self.assertEqual(self.recruiter_open(application.application_id, with_cv=with_cv, **changes).status_code, 400)
        self.assertEqual(application.application_status, "SUBMITTED")

    def test_view_before_replace_blocks_replacement(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        self.login(self.recruiter)
        self.assertEqual(self.recruiter_open(application.application_id).status_code, 200)
        self.login(self.candidate)
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 409)
        self.assertEqual(application.cv_id, self.cv_id)

    def test_replace_before_view_returns_new_cv_and_blocks_later_replacement(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        Path(new_cv.file_path).write_bytes(b"New submitted synthetic CV")
        db.session.commit()
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
        self.login(self.recruiter)
        response = self.recruiter_open(application.application_id, with_cv=True)
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"New submitted synthetic CV")
        finally:
            response.close()
        self.login(self.candidate)
        self.assertEqual(self.replacement(application.application_id, self.cv_id).status_code, 409)

    def test_hidden_target_blocks_replacement_and_current_submitted_cv_cannot_be_hidden(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        self.assertEqual(self.visibility(cv_id=new_cv.cv_id).status_code, 200)
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 400)
        self.assertEqual(self.visibility(cv_id=new_cv.cv_id, is_hidden="0").status_code, 200)
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
        self.assertEqual(self.visibility(cv_id=new_cv.cv_id).status_code, 400)
        self.assertFalse(new_cv.is_hidden)
        self.login(self.recruiter)
        response = self.recruiter_open(application.application_id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["application"]["cv_id"], new_cv.cv_id)

    def test_stale_view_hint_retries_and_opens_new_cv_instead_of_old_cv(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        Path(new_cv.file_path).write_bytes(b"New submitted synthetic CV")
        db.session.commit()
        application.cv_id = new_cv.cv_id
        db.session.commit()
        original_first, hints = Query.first, []

        def stale_once(query):
            if query._for_update_arg is None and query.column_descriptions[0]["name"] == "cv_id":
                hints.append(True)
                if len(hints) == 1:
                    return SimpleNamespace(cv_id=self.cv_id, user_id=self.candidate_id, job_id=self.job_id)
            return original_first(query)

        self.login(self.recruiter)
        with patch.object(Query, "first", stale_once):
            response = self.recruiter_open(application.application_id, with_cv=True)
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"New submitted synthetic CV")
        finally:
            response.close()
        self.assertEqual(len(hints), 2)
        self.assertEqual(application.application_status, "VIEWED")

    def test_stale_replacement_hint_retries_and_checks_latest_application(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        application.cv_id = new_cv.cv_id
        db.session.commit()
        original_first, hints = Query.first, []

        def stale_once(query):
            if query._for_update_arg is None and query.column_descriptions[0]["name"] == "cv_id":
                hints.append(True)
                if len(hints) == 1:
                    return SimpleNamespace(cv_id=self.cv_id)
            return original_first(query)

        with patch.object(Query, "first", stale_once):
            self.assertEqual(self.replacement(application.application_id, self.cv_id).status_code, 200)
        self.assertEqual(len(hints), 2)
        self.assertEqual(application.cv_id, self.cv_id)

    def test_persistent_hint_mismatch_is_bounded_and_returns_retry_error(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        original_first, hints = Query.first, []

        def always_stale(query):
            if query._for_update_arg is None and query.column_descriptions[0]["name"] == "cv_id":
                hints.append(True)
                return SimpleNamespace(cv_id=new_cv.cv_id, user_id=self.candidate_id, job_id=self.job_id)
            return original_first(query)

        with patch.object(Query, "first", always_stale):
            response = self.replacement(application.application_id, new_cv.cv_id)
        self.assertEqual(response.status_code, 409)
        self.assertIn("concurrency", response.json["errors"])
        self.assertEqual(len(hints), 3)
        hints.clear()
        self.login(self.recruiter)
        with patch.object(Query, "first", always_stale):
            response = self.recruiter_open(application.application_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(hints), 3)
        self.assertEqual((application.cv_id, application.application_status), (self.cv_id, "SUBMITTED"))

    def test_visibility_and_replacement_rollback_after_flush(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()

        def fail_commit():
            db.session.flush()
            raise SQLAlchemyError("synthetic commit failure")

        with patch.object(db.session, "commit", side_effect=fail_commit), self.assertLogs(self.app.logger, level="ERROR"):
            self.assertEqual(self.visibility(cv_id=new_cv.cv_id).status_code, 400)
            self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 503)
        self.assertFalse(self.cv.is_hidden)
        self.assertFalse(new_cv.is_hidden)
        self.assertEqual((application.cv_id, application.application_status), (self.cv_id, "SUBMITTED"))
        self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)

    def test_view_rollback_after_flush_closes_file_and_does_not_mark_viewed(self):
        application = self.existing_application()
        self.login(self.recruiter)
        opened, actual_open = [], open

        def tracked_open(*args, **kwargs):
            handle = actual_open(*args, **kwargs)
            opened.append(handle)
            return handle

        def fail_commit():
            db.session.flush()
            raise SQLAlchemyError("synthetic commit failure")

        with patch("app.services.application_service.open", tracked_open, create=True), patch.object(db.session, "commit", side_effect=fail_commit), self.assertLogs(self.app.logger, level="ERROR"):
            response = self.recruiter_open(application.application_id, with_cv=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(application.application_status, "SUBMITTED")
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].closed)

    def test_missing_cv_file_does_not_mark_application_viewed(self):
        application = self.existing_application()
        Path(self.cv.file_path).unlink()
        self.login(self.recruiter)
        self.assertEqual(self.recruiter_open(application.application_id, with_cv=True).status_code, 404)
        self.assertEqual(application.application_status, "SUBMITTED")

    def test_lock_order_and_refresh_for_replace_visibility_delete_and_view(self):
        application = self.existing_application()
        new_cv = self.new_cv(self.candidate, "replacement.pdf")
        db.session.commit()
        locked = []

        def capture(state):
            if state.is_select and getattr(state.statement, "_for_update_arg", None) is not None:
                entity = state.statement.column_descriptions[0]["entity"]
                locked.append((entity, state.statement, getattr(state.load_options, "_populate_existing", False)))

        event.listen(db.session(), "do_orm_execute", capture)
        try:
            self.assertEqual(self.replacement(application.application_id, new_cv.cv_id).status_code, 200)
            self.assertEqual([row[0] for row in locked], [User, CV, CV, Application])
            cv_parameters = [list(row[1].compile().params.values())[0] for row in locked if row[0] is CV]
            self.assertEqual(cv_parameters, sorted([self.cv_id, new_cv.cv_id]))
            locked.clear()
            self.assertEqual(self.visibility(cv_id=new_cv.cv_id).status_code, 400)
            self.assertEqual([row[0] for row in locked], [User, CV, Application])
            for _, statement, _ in locked:
                self.assertIn("FOR UPDATE", str(statement.compile(dialect=mysql.dialect())))
            # Trạng thái đọc trực tiếp là cột scalar, không dựa vào Application trong identity map.
            self.assertEqual(locked[-1][1].column_descriptions[0]["name"], "application_status")
            locked.clear()
            self.assertFalse(delete_cv(self.candidate_id, new_cv.cv_id)[0])
            self.assertEqual([row[0] for row in locked], [User, CV, Application])
            locked.clear()
            self.login(self.recruiter)
            self.assertEqual(self.recruiter_open(application.application_id).status_code, 200)
            self.assertEqual([row[0] for row in locked], [User, CV, Job, Application])
            for _, statement, refresh in locked:
                self.assertTrue(refresh)
                self.assertIn("FOR UPDATE", str(statement.compile(dialect=mysql.dialect())))
        finally:
            event.remove(db.session(), "do_orm_execute", capture)


if __name__ == "__main__":
    unittest.main()
