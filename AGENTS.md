# AGENTS.md — JobFit Development Guidelines

## 1. Project Overview

JobFit là hệ thống website hỗ trợ tuyển dụng và đánh giá mức độ phù hợp giữa CV của ứng viên và mô tả công việc (JD).

Công nghệ sử dụng:
- Backend: Python 3.10, Flask, Flask-SQLAlchemy, SQLAlchemy.
- Database: MySQL.
- Frontend: HTML, CSS, Bootstrap, JavaScript, Jinja2.
- Architecture: MVC kết hợp Service Layer và Flask Blueprint.

Dự án đang được phát triển. Nhiều chức năng đã hoàn thiện và phải được bảo toàn.

## 2. Project Architecture

Tuân thủ cấu trúc hiện tại:

- `app/controllers/`: Flask Blueprints, routes, request handling, authorization và điều hướng.
- `app/models/`: SQLAlchemy models và quan hệ database.
- `app/services/`: Business logic, xử lý CV, JD và kỹ năng.
- `app/middleware/`: Authentication và authorization.
- `app/templates/`: Giao diện Jinja2.
- `app/static/`: CSS, JavaScript, hình ảnh và tài nguyên tĩnh.
- `migrations/`: Database migrations.
- `scripts/`: Seed dữ liệu.
- `tests/`: Kiểm thử.

Không tự ý tạo thư mục `routes/`, chuyển Blueprint hoặc tái cấu trúc dự án.

## 3. Mandatory Development Rules

1. Đọc và hiểu code hiện tại trước khi đề xuất chỉnh sửa.
2. Ưu tiên tái sử dụng các hàm, Service và Model đã có.
3. Chỉ sửa các file thực sự liên quan đến nhiệm vụ.
4. Không tự ý xóa, đổi tên file hoặc viết lại toàn bộ module.
5. Không thay đổi URL, tên Blueprint, endpoint hoặc tham số `url_for()` nếu không được yêu cầu.
6. Không tự ý thay đổi database schema, migration hoặc seed data.
7. Trước khi sửa, phải trình bày kế hoạch và chờ người dùng phê duyệt.
8. Không tự ý cài đặt thư viện hoặc thay đổi `requirements.txt`.
9. Không tự ý chạy Git commit, push, reset hoặc các lệnh có khả năng làm mất dữ liệu.
10. Không chỉnh sửa chức năng ngoài phạm vi được giao nếu chưa được đồng ý.

## 4. Security Requirements

- Kiểm tra authentication, authorization, role và ownership ở các thao tác quan trọng.
- Bảo toàn CSRF protection, session và password hashing.
- Validate dữ liệu đầu vào và file upload.
- Sử dụng SQLAlchemy an toàn, tránh SQL injection.
- Không đọc hoặc tiết lộ nội dung `.env`, mật khẩu, API key và thông tin bí mật.
- Không tự ý xóa dữ liệu MySQL hoặc chạy lệnh thay đổi database.
- Không đưa CV cá nhân, dữ liệu riêng tư hoặc file upload lên GitHub.

## 5. Existing Business Rules

### Recruiter
- Recruiter được đăng tin tuyển dụng trực tiếp, không cần Admin duyệt.
- Chỉ quản lý tin thuộc công ty của mình.
- Trạng thái hiển thị ưu tiên: HIDDEN → CLOSED → EXPIRED → OPEN.
- Tin đã đóng vẫn hiển thị CLOSED dù đã quá hạn.
- Không được mở lại tin đã hết hạn.
- Chỉ sửa nội dung tối đa 1 lần khi tin OPEN, không bị ẩn, còn hạn và chưa từng có ứng viên; hồ sơ đã rút vẫn tính là từng có ứng viên.
- Các trường sửa nội dung: min_salary, max_salary, location, working_time, benefit. Không sửa tiêu đề, JD, yêu cầu ứng viên hoặc bộ kỹ năng.
- Lưu content_edit_count trong database; chỉ tăng lượt khi nội dung thực sự thay đổi và transaction thành công. Mở form, hủy, không thay đổi hoặc lưu lỗi không mất lượt.
- Tăng số lượng tuyển và gia hạn là hai thao tác riêng, không mất lượt; không cho giảm số lượng hoặc rút ngắn thời hạn, kể cả khi chưa có ứng viên.
- Khi có ứng viên hoặc hết lượt sửa nội dung, chỉ được tăng số lượng và gia hạn nếu tin OPEN, không bị ẩn và còn hạn. Tin HIDDEN, CLOSED, EXPIRED hoặc quá hạn không được sửa hay điều chỉnh.
- Đóng/mở lại không khôi phục lượt sửa. Khi hết lượt, có thể đóng tin và đăng tin mới; không xóa tin cũ hoặc lịch sử ứng tuyển.
- Form sửa nội dung phải cảnh báo: "Bạn chỉ được chỉnh sửa thông tin tin tuyển dụng 1 lần duy nhất. Vui lòng kiểm tra kỹ trước khi lưu."
- Admin có quyền ẩn tin vi phạm, không sửa nội dung thay Recruiter.
- Luồng đăng tin: Tạo tin → Kiểm tra kỹ năng → Xác nhận → Đăng tuyển.

### Candidate
- Bảo toàn chức năng hồ sơ, CV và các luồng ứng tuyển hiện tại.
- Không thay đổi cách lưu trữ hoặc xử lý CV khi chưa kiểm tra các Service liên quan.

### Admin
- Sử dụng layout riêng.
- Bảo toàn chức năng quản lý tài khoản và tin tuyển dụng.
- Không tự ý thay đổi quy tắc khóa/mở khóa hoặc ẩn tin.

### CV–JD Matching
- Tái sử dụng các Service xử lý CV, trích xuất kỹ năng và fuzzy matching hiện tại.
- Không tự ý thay thế thuật toán hoặc mô hình đánh giá.
- Khi sửa kỹ năng, kiểm tra ảnh hưởng đến Skill, SkillAlias, JobSkill và CandidateSkill.
- Không tự ý thay đổi cách tính điểm phù hợp khi chưa có yêu cầu.

## 6. UI/UX Guidelines

- Giữ nguyên phong cách giao diện JobFit.
- Recruiter sử dụng sidebar trắng, nền ngoài `#F7F9FC`.
- Recruiter sử dụng `recruiter_base.html`; Admin sử dụng layout riêng.
- Không tự ý thay đổi header, footer hoặc cấu trúc điều hướng.
- Khi sửa template, kiểm tra Controller, Service, Model, form, session, CSRF và `url_for()` liên quan.
- Ưu tiên HTML gọn, dễ đọc, hạn chế dòng trống không cần thiết.

## 7. Code Quality

- Viết code rõ ràng, dễ bảo trì.
- Thêm comment tiếng Việt ngắn gọn ở các đoạn xử lý quan trọng.
- Không thêm thư viện hoặc abstraction không cần thiết.
- Không tạo code trùng lặp khi đã có hàm xử lý tương đương.
- Không làm thay đổi hành vi của chức năng khác ngoài yêu cầu.

## 8. Required Workflow

Với mỗi yêu cầu phát triển:

1. Phân tích yêu cầu và code liên quan.
2. Xác định những file cần đọc và chỉnh sửa.
3. Trình bày kế hoạch thực hiện.
4. Chờ người dùng xác nhận trước khi sửa.
5. Thực hiện thay đổi tối thiểu.
6. Chạy kiểm thử phù hợp nếu được phép.
7. Báo cáo file đã sửa, nội dung thay đổi, kết quả kiểm thử và những vấn đề còn tồn tại.

Không tuyên bố đã kiểm thử thành công nếu chưa thực sự chạy kiểm thử.

## 9. First Interaction

Trong lần đầu làm việc với repository:

- Chỉ đọc và phân tích kiến trúc hiện tại.
- Tóm tắt các module, chức năng và luồng xử lý.
- Xác định những điểm cần lưu ý khi tiếp tục phát triển.
- Không chỉnh sửa bất kỳ file nào.
- Chờ yêu cầu tiếp theo từ người dùng.
