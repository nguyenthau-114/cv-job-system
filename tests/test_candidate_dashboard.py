"""Dashboard Candidate: dữ liệu giả trên SQLite RAM, không đọc .env/MySQL."""
from datetime import datetime
import re
import unittest
from unittest.mock import patch

from flask import template_rendered
from sqlalchemy import event, select

import tests.test_workspace_layout as layouts
from app.extensions import db
from app.models.application import Application
from app.models.cv import CV
from app.models.job import Job
from app.models.user import User
from app.services.application_service import get_candidate_dashboard


class CandidateDashboardTests(unittest.TestCase):
    def setUp(self):
        # Tái sử dụng factory test có cấu hình SQLite và bật FK/CSRF.
        self.layout = layouts.WorkspaceLayoutTests()
        self.layout.setUp()
        self.addCleanup(self.layout.doCleanups)
        self.app = self.layout.app
        self.client = self.layout.client
        self.candidate = self.layout.candidate
        self.cv = self.layout.cv
        self.other = User(user_name="Other candidate", email="other@example.invalid",
                          password_hash="unused", role="CANDIDATE", email_verified=True)
        db.session.add(self.other)
        db.session.flush()
        self.other_cv = CV(user_id=self.other.user_id, file_name="other.pdf",
                           file_path="synthetic-only", file_type="PDF", is_hidden=True)
        db.session.add(self.other_cv)
        db.session.commit()
        self.layout.login(self.candidate)
        self.sequence = 0

    def new_application(self, status="SUBMITTED", when=None, user=None, cv=None):
        user = user or self.candidate
        cv = cv or (self.cv if user == self.candidate else self.other_cv)
        self.sequence += 1
        job = Job(company_id=self.layout.company.company_id,
                  job_category_id=self.layout.category.job_category_id,
                  job_title=f"Synthetic position {self.sequence:02d}", job_slug=f"position-{self.sequence}",
                  job_description="Synthetic JD", job_requirement="Synthetic requirement",
                  experience="1 year", level="JUNIOR", quantity=1, work_mode="ONSITE",
                  job_type="FULL_TIME", location="Synthetic location",
                  application_deadline=self.layout.job.application_deadline)
        db.session.add(job)
        db.session.flush()
        application = Application(user_id=user.user_id, cv_id=cv.cv_id, job_id=job.job_id,
                                  contact_name="Application contact", contact_email="contact@example.invalid",
                                  contact_phone="0900000001", cover_letter="Synthetic introduction",
                                  application_status=status, applied_at=when or datetime(2026, 10, 26, 12))
        db.session.add(application)
        db.session.commit()
        return application, job

    def dashboard(self, path="/candidate/"):
        contexts = []

        def capture(sender, template, context, **extra):
            if template.name == "candidate/dashboard.html":
                contexts.append(context)

        with template_rendered.connected_to(capture, self.app):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(contexts), 1)
        return response.get_data(as_text=True), contexts[0]

    def test_empty_candidate_has_zero_statistics_and_job_search_link(self):
        db.session.delete(self.cv)
        db.session.commit()
        html, context = self.dashboard()
        self.assertEqual(context["statistics"], {"cvs": 0, "applications": 0, "reviewing": 0, "viewed": 0})
        self.assertEqual(context["recent_applications"], [])
        self.assertIn("Bạn chưa có đơn ứng tuyển nào", html)
        self.assertTrue(layouts.Elements(html).find("a", href="/jobs"))

    def test_cv_count_includes_hidden_and_all_analysis_states_only_for_owner(self):
        for status, hidden in (("PENDING", True), ("COMPLETED", False), ("FAILED", True)):
            db.session.add(CV(user_id=self.candidate.user_id, file_name=f"{status}.pdf",
                              file_path="synthetic-only", file_type="PDF", analysis_status=status,
                              is_hidden=hidden))
        db.session.commit()
        result = get_candidate_dashboard(self.candidate.user_id)
        self.assertEqual(result["statistics"]["cvs"], 4)
        self.assertEqual(get_candidate_dashboard(self.other.user_id)["statistics"]["cvs"], 1)

    def test_statistics_include_withdrawn_and_only_current_review_states(self):
        for status in ("SUBMITTED", "VIEWED", "CONSIDERING", "INTERVIEW", "REJECTED", "WITHDRAWN",
                       "VIEWED", "UNKNOWN"):
            self.new_application(status)
        result = get_candidate_dashboard(self.candidate.user_id)
        self.assertEqual(result["statistics"], {"cvs": 1, "applications": 8, "reviewing": 5, "viewed": 2})

    def test_viewed_statistic_is_not_lifetime_view_count(self):
        application, _ = self.new_application("VIEWED")
        self.assertEqual(get_candidate_dashboard(self.candidate.user_id)["statistics"]["viewed"], 1)
        application.application_status = "CONSIDERING"
        db.session.commit()
        stats = get_candidate_dashboard(self.candidate.user_id)["statistics"]
        self.assertEqual((stats["applications"], stats["reviewing"], stats["viewed"]), (1, 1, 0))

    def test_application_owner_is_not_inferred_from_cv_owner(self):
        # Dữ liệu giả cố ý lệch chủ CV để bắt lỗi lọc Application qua CV.user_id.
        owned, _ = self.new_application("SUBMITTED", cv=self.other_cv)
        foreign, foreign_job = self.new_application("VIEWED", user=self.other, cv=self.cv)
        html, context = self.dashboard(f"/candidate/?user_id={self.other.user_id}")
        self.assertEqual(context["statistics"], {"cvs": 1, "applications": 1, "reviewing": 1, "viewed": 0})
        self.assertEqual([row.application_id for row in context["recent_applications"]], [owned.application_id])
        self.assertNotIn(foreign_job.job_title, html)
        self.layout.login(self.other)
        _, other_context = self.dashboard()
        self.assertEqual([row.application_id for row in other_context["recent_applications"]],
                         [foreign.application_id])

    def test_recent_applications_limit_order_and_tie_break_are_deterministic(self):
        applications = [self.new_application(when=datetime(2026, 10, day, 12))[0]
                        for day in (6, 1, 8, 3, 8, 2, 4, 5)]
        self.new_application(user=self.other, when=datetime(2026, 11, 1))
        _, context = self.dashboard()
        self.assertEqual([row.application_id for row in context["recent_applications"]],
                         [applications[index].application_id for index in (4, 2, 0, 7, 6)])
        self.assertEqual(context["statistics"]["applications"], 8)

    def test_recent_rows_include_company_date_and_do_not_link_to_missing_detail(self):
        application, job = self.new_application("WITHDRAWN", when=datetime(2026, 10, 23, 14, 30))
        job.job_status = "CLOSED"
        job.is_hidden = True
        db.session.commit()
        html, context = self.dashboard()
        self.assertIn(job.job_title, html)
        self.assertIn(self.layout.company.company_name, html)
        self.assertIn("23/10/2026", re.sub(r"<[^>]*>", "", html))
        self.assertIn("Đã rút đơn", html)
        self.assertEqual(context["recent_applications"][0].application_id, application.application_id)
        links = layouts.Elements(html).find("a")
        self.assertFalse(any("/candidate/applications/" in link.get("href", "") for link in links))

    def test_status_labels_and_unknown_fallback_render(self):
        for status, label in (("SUBMITTED", "Đã nộp"), ("VIEWED", "Đã xem hồ sơ"),
                              ("CONSIDERING", "Đang cân nhắc"), ("INTERVIEW", "Đang phỏng vấn"),
                              ("REJECTED", "Đã từ chối"), ("WITHDRAWN", "Đã rút đơn"),
                              ("UNKNOWN", "Chưa xác định")):
            with self.subTest(status=status):
                self.new_application(status)
                html, _ = self.dashboard()
                table = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
                self.assertIn(label, table)

    def test_job_and_company_text_are_escaped(self):
        _, job = self.new_application()
        job.job_title = "<script>synthetic</script>"
        self.layout.company.company_name = "<b>Synthetic company</b>"
        db.session.commit()
        html, _ = self.dashboard()
        self.assertIn("&lt;script&gt;synthetic&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Synthetic company&lt;/b&gt;", html)
        self.assertNotIn("<script>synthetic</script>", html)

    def test_dashboard_get_only_reads_and_leaves_all_records_unchanged(self):
        self.new_application("SUBMITTED")
        self.new_application("VIEWED")

        def snapshot():
            return {table.name: db.session.execute(select(table)).all()
                    for table in db.metadata.sorted_tables}

        before = snapshot()
        statements = []

        def record(connection, cursor, statement, parameters, context, executemany):
            statements.append(statement.lstrip().split(None, 1)[0].upper())

        event.listen(db.engine, "before_cursor_execute", record)
        try:
            with patch.object(db.session, "commit", side_effect=AssertionError("Dashboard must not commit")), \
                    patch("app.controllers.recruiter_controller.open_recruiter_application",
                          side_effect=AssertionError("Dashboard must not mark VIEWED")):
                self.dashboard()
        finally:
            event.remove(db.engine, "before_cursor_execute", record)
        self.assertTrue(statements)
        self.assertEqual(set(statements), {"SELECT"})
        self.assertEqual(snapshot(), before)

    def test_dashboard_requires_active_candidate_and_database_role(self):
        for user in (None, self.layout.recruiter, self.layout.admin):
            with self.subTest(role=user.role if user else "guest"):
                self.layout.login(user)
                with patch("app.controllers.candidate_controller.get_candidate_dashboard") as read_data:
                    self.assertEqual(self.client.get("/candidate/").status_code, 302)
                    read_data.assert_not_called()
        self.candidate.user_status = "LOCKED"
        db.session.commit()
        self.layout.login(self.candidate)
        with patch("app.controllers.candidate_controller.get_candidate_dashboard") as read_data:
            self.assertEqual(self.client.get("/candidate/").status_code, 302)
            read_data.assert_not_called()

    def test_dashboard_ignores_spoofed_session_role(self):
        self.layout.login(self.layout.recruiter)
        with self.client.session_transaction() as current:
            current["role"] = "CANDIDATE"
        with patch("app.controllers.candidate_controller.get_candidate_dashboard") as read_data:
            self.assertEqual(self.client.get("/candidate/").status_code, 302)
            read_data.assert_not_called()

    def test_stat_cards_have_no_icons_and_navigation_remains_active(self):
        html, _ = self.dashboard()
        stats_html = html.split('candidate-dashboard-stats">', 1)[1].split('<div class="card mb-3">', 1)[0]
        elements = layouts.Elements(stats_html)
        self.assertEqual(len(elements.find("div", **{"class": "col-6 col-lg-3"})), 4)
        self.assertFalse(elements.find("i"))
        self.assertFalse(elements.find("svg"))
        self.assertNotIn("min-height", stats_html)
        self.assertIn("Tổng quan ứng viên", html)
        self.assertEqual([item["href"] for item in self.layout.active_links(html, "workspace")], ["/candidate/"])
        self.assertTrue(layouts.Elements(html).find("a", href="/candidate/cvs"))
        self.assertTrue(layouts.Elements(html).find("a", href="/jobs"))


if __name__ == "__main__":
    unittest.main()
