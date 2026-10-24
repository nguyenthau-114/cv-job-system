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
- Candidate chỉ được ẩn CV của mình khi không có Application tham chiếu hoặc tất cả đơn tham chiếu có trạng thái chính xác REJECTED hoặc WITHDRAWN. Chặn ẩn nếu còn SUBMITTED, VIEWED, CONSIDERING, INTERVIEW hoặc bất kỳ trạng thái khác, kể cả NULL, chuỗi rỗng và trạng thái không xác định. Kiểm tra mọi đơn, kể cả khi CV đã có is_hidden = TRUE.
- Candidate luôn được hiện lại CV thuộc tài khoản của mình, không chặn vì Application đang tham chiếu. Ẩn/hiện không thay đổi Application hoặc dữ liệu phân tích kỹ năng.
- Lưu is_hidden trong database, NOT NULL và mặc định FALSE; CV hiện có giữ trạng thái hiển thị. Backend Giai đoạn 2.5B đã triển khai ẩn/hiện, thay CV và ghi nhận VIEWED; giao diện được triển khai ở giai đoạn sau.

### Application — Quy tắc ứng tuyển đã chốt
- Chỉ Candidate đăng nhập và đang hoạt động được nộp đơn vào tin OPEN, còn hạn, không bị Admin ẩn; phải kiểm tra lại tại thời điểm lưu.
- Chỉ chọn CV đã lưu thuộc tài khoản Candidate và không bị ẩn, kể cả khi ứng tuyển mới hoặc thay CV đã nộp. Không upload trực tiếp trong form ứng tuyển và không bắt buộc CV đã phân tích kỹ năng xong.
- Mỗi Candidate chỉ ứng tuyển một lần vào mỗi Job, kể cả đổi CV hoặc đơn đã rút. Database sử dụng unique constraint uq_application_user_job(user_id, job_id).
- Họ tên, email và số điện thoại đều bắt buộc. Tự điền từ tài khoản nếu có, cho phép sửa, nhưng chỉ lưu thông tin riêng vào Application và không cập nhật User.
- Thư giới thiệu không bắt buộc, tối đa 5.000 ký tự; kiểm tra độ dài tại backend khi triển khai luồng nộp đơn.
- Candidate chưa có CV được hướng dẫn tới trang Quản lý CV.
- Sau đăng nhập có thể quay lại đúng công việc/form ứng tuyển bằng next nội bộ đã kiểm tra an toàn, không tạo open redirect.
- CV còn được bất kỳ Application nào tham chiếu không được xóa, kể cả đơn đã rút; phải giải thích rõ lý do và giữ nguyên file/lịch sử. Sau khi thay CV, CV cũ chỉ được xóa nếu không còn Application nào tham chiếu.
- REJECTED và WITHDRAWN là hai trạng thái kết thúc cho phép ẩn CV nếu mọi đơn tham chiếu đều đã kết thúc; vẫn không cho xóa CV còn tham chiếu. Luồng ẩn CV phải giữ thứ tự khóa User → CV → Application, đồng bộ với nộp đơn và thay CV.
- Candidate chỉ được thay CV khi Recruiter chưa xem hồ sơ, Application còn SUBMITTED. Không cho thay khi VIEWED, đang xử lý, REJECTED, WITHDRAWN hoặc trạng thái không xác định; CV thay thế phải thuộc Candidate và không bị ẩn.
- Thay CV chỉ cập nhật cv_id của Application hiện tại, không tạo đơn mới. Giữ nguyên applied_at, thông tin liên hệ, thư giới thiệu, trạng thái và các trường khác của đơn.
- Không cho trạng thái đã xem hoặc xử lý quay lại SUBMITTED. Việc đánh dấu đã xem phải được thực hiện tại backend của luồng Recruiter mở hồ sơ/CV, không dựa vào trạng thái đọc thông báo.
- Job đã từng có Application không được sửa nội dung. Tăng số lượng và gia hạn vẫn theo điều kiện OPEN, còn hạn, không bị ẩn.
- quantity là số lượng cần tuyển, không giới hạn số Application và không bị giảm khi nhận đơn.
- Nộp đơn không tự xác nhận kỹ năng, không đánh dấu CV đã phân tích xong và không thay đổi quy trình CV–JD.
- Recruiter chỉ được xem đơn, thông tin liên hệ, thư giới thiệu và CV thuộc Job của công ty mình. Chưa triển khai duyệt/từ chối hoặc mời phỏng vấn.
- Recruiter vẫn được xem CV đã nộp qua Application thuộc Job của công ty mình, kể cả khi Candidate ẩn CV sau khi đơn kết thúc. Không dùng bộ lọc CV được phép chọn để chặn truy cập hồ sơ đã nộp.
- Card /jobs có Xem nhanh, Xem chi tiết, Ứng tuyển ngay và Yêu thích. Yêu thích giữ nguyên hiện trạng, chưa triển khai backend.
- Trang danh sách và trang chi tiết dùng chung form và backend ứng tuyển. Đây là quy tắc đích, chỉ triển khai theo từng giai đoạn đã được phê duyệt.
- Không thêm cascade xóa Application theo User, CV hoặc Job. Migration phải kiểm tra dữ liệu cũ trước DDL, không tự xóa, gộp hoặc tạo thông tin giả.

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
