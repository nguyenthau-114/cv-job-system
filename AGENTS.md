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
- Các trường sửa nội dung: min_salary, max_salary, location, working_time, benefit. Không sửa tiêu đề, JD, yêu cầu ứng viên, kinh nghiệm hoặc bộ kỹ năng.
- Lưu content_edit_count trong database; chỉ tăng lượt khi nội dung thực sự thay đổi và transaction thành công. Mở form, hủy, không thay đổi hoặc lưu lỗi không mất lượt.
- Tăng số lượng tuyển và gia hạn là hai thao tác riêng, không mất lượt; không cho giảm số lượng hoặc rút ngắn thời hạn, kể cả khi chưa có ứng viên.
- Khi có ứng viên hoặc hết lượt sửa nội dung, chỉ được tăng số lượng và gia hạn nếu tin OPEN, không bị ẩn và còn hạn. Tin HIDDEN, CLOSED, EXPIRED hoặc quá hạn không được sửa hay điều chỉnh.
- Đóng/mở lại không khôi phục lượt sửa. Khi hết lượt, có thể đóng tin và đăng tin mới; không xóa tin cũ hoặc lịch sử ứng tuyển.
- Form sửa nội dung phải cảnh báo: "Bạn chỉ được chỉnh sửa thông tin tin tuyển dụng 1 lần duy nhất. Vui lòng kiểm tra kỹ trước khi lưu."
- Admin có quyền ẩn tin vi phạm, không sửa nội dung thay Recruiter.
- Luồng đăng tin: Tạo tin → Kiểm tra kỹ năng → Xác nhận → Đăng tuyển.
- Chuẩn hóa kinh nghiệm đầu vào trong job_service.py khi kiểm tra form và lưu tin: bỏ khoảng trắng thừa, chuẩn hóa khoảng số và rút gọn các mẫu năm/tháng có hậu tố "kinh nghiệm" đã nhận diện chắc chắn. Giữ nghĩa mô tả tự do, không suy diễn đơn vị cho số đơn lẻ. Kinh nghiệm bắt buộc, tối đa 100 ký tự sau chuẩn hóa. Không tự cập nhật dữ liệu MySQL cũ; kinh nghiệm không được sửa sau khi đăng Job.
- Đợt 2B: Recruiter quản lý hồ sơ tại /recruiter/applications, tìm theo thông tin liên hệ đã nộp trong Application, lọc Job/trạng thái và phân trang. Mọi truy vấn, bộ đếm và danh sách Job lựa chọn phải giới hạn theo công ty của Recruiter đang hoạt động trước khi lọc/đếm/phân trang.
- Danh sách, tìm kiếm, lọc và GET chi tiết không tự đánh dấu VIEWED. Đơn SUBMITTED trên trang GET chỉ có dữ liệu chờ mở, chưa đưa email, điện thoại, thư giới thiệu hoặc CV vào View. Nút mở hồ sơ và CV dùng POST có CSRF qua Application; chỉ SUBMITTED được chuyển thành VIEWED, không ghi đè trạng thái khác.
- Cho phép VIEWED → CONSIDERING, VIEWED → REJECTED và CONSIDERING → REJECTED. INTERVIEW chỉ xem lịch sử trong Đợt 2B. REJECTED/WITHDRAWN và trạng thái không xác định không được chuyển sang trạng thái xét tuyển khác. Gửi lại đúng CONSIDERING/REJECTED hiện tại là no-op nếu Job vẫn hợp lệ và không bị ẩn.
- Job CLOSED/EXPIRED vẫn được tiếp tục xử lý hồ sơ cũ. Job bị Admin ẩn chỉ được xem lịch sử và ghi nhận thao tác mở hồ sơ/CV theo backend hiện có, không được chuyển CONSIDERING/REJECTED. Bỏ ẩn cho phép tiếp tục xử lý hồ sơ đủ điều kiện. Backend phải đọc lại Job và Application dưới khóa, không dựa vào quyền trên giao diện.
- Luồng mở và xét tuyển khóa User actor/người nhận theo ID tăng dần (actor khóa độc quyền, người nhận khóa chia sẻ), rồi CV Candidate → Job → Application, kiểm tra lại ownership và cv_id. Rút đơn trước thì chặn xét tuyển, từ chối trước thì Candidate không thể rút, chuyển CONSIDERING trước vẫn cho Candidate rút theo quy tắc hiện có. Đổi trạng thái xét tuyển chỉ cập nhật application_status, giữ nguyên thông tin và các trường khác; Notification được thêm trong cùng transaction.

### Candidate
- Bảo toàn chức năng hồ sơ, CV và các luồng ứng tuyển hiện tại.
- Không thay đổi cách lưu trữ hoặc xử lý CV khi chưa kiểm tra các Service liên quan.
- Candidate chỉ được ẩn CV của mình khi không có Application tham chiếu hoặc tất cả đơn tham chiếu có trạng thái chính xác REJECTED hoặc WITHDRAWN. Chặn ẩn nếu còn SUBMITTED, VIEWED, CONSIDERING, INTERVIEW hoặc bất kỳ trạng thái khác, kể cả NULL, chuỗi rỗng và trạng thái không xác định. Kiểm tra mọi đơn, kể cả khi CV đã có is_hidden = TRUE.
- Candidate luôn được hiện lại CV thuộc tài khoản của mình, không chặn vì Application đang tham chiếu. Ẩn/hiện không thay đổi Application hoặc dữ liệu phân tích kỹ năng.
- Lưu is_hidden trong database, NOT NULL và mặc định FALSE; CV hiện có giữ trạng thái hiển thị. Đợt 2A đã nối giao diện Candidate với backend ẩn/hiện CV và thay CV. Luồng Recruiter ghi nhận VIEWED vẫn thực hiện tại backend khi mở hồ sơ/CV.
- Candidate xem danh sách đơn tại /candidate/applications, lọc trạng thái và phân trang; chi tiết tại /candidate/applications/<application_id>. Luôn lọc theo Application.user_id của tài khoản đang đăng nhập. Thông tin liên hệ và thư giới thiệu lấy từ Application, không thay bằng dữ liệu User hiện tại.
- Dashboard, danh sách và chi tiết đơn phải che thông tin Job/công ty khi tin bị Admin ẩn, không đưa JD, kỹ năng hoặc liên kết chi tiết công khai vào View. Candidate vẫn xem được dữ liệu Application, thư giới thiệu và CV của mình. Tin CLOSED/EXPIRED chỉ hiện thông tin cơ bản và lý do ngừng tuyển, CLOSED ưu tiên trước hết hạn.
- Candidate xem đơn hoặc CV của mình không đánh dấu VIEWED. Chỉ hiển thị trạng thái hiện tại, không suy diễn lịch sử chuyển trạng thái hoặc thời điểm đã xem khi chưa có dữ liệu.
- Lưu/bỏ lưu tin chỉ dành cho Candidate đang hoạt động, sử dụng bảng saved_jobs và unique constraint uq_saved_job_user_job(user_id, job_id). Đặt trạng thái lưu tường minh để gửi lại không đảo trạng thái. Lưu tin độc lập với Application, không yêu cầu có CV và không thay đổi đơn đã nộp.
- Trang Việc làm đã lưu tại /candidate/saved-jobs lọc theo chủ tài khoản và có phân trang. Tin OPEN công khai, còn hạn được xem chi tiết và ứng tuyển nếu đủ điều kiện. Tin CLOSED hoặc EXPIRED chỉ hiện thông tin cơ bản, không có liên kết chi tiết hoặc ứng tuyển. CLOSED ưu tiên trước hết hạn.
- Tin bị Admin ẩn trong danh sách đã lưu chỉ hiện "Tin tuyển dụng hiện không còn khả dụng.", không đưa tiêu đề, công ty, JD hoặc kỹ năng vào HTML/dữ liệu của card. Candidate vẫn được bỏ lưu tin đã đóng, hết hạn hoặc không khả dụng.

### Application — Quy tắc ứng tuyển đã chốt
- Chỉ Candidate đăng nhập và đang hoạt động được nộp đơn vào tin OPEN, còn hạn, không bị Admin ẩn; phải kiểm tra lại tại thời điểm lưu.
- Chỉ chọn CV đã lưu thuộc tài khoản Candidate và không bị ẩn, kể cả khi ứng tuyển mới hoặc thay CV đã nộp. Không upload trực tiếp trong form ứng tuyển và không bắt buộc CV đã phân tích kỹ năng xong.
- Mỗi Candidate chỉ ứng tuyển một lần vào mỗi Job, kể cả đổi CV hoặc đơn đã rút. Database sử dụng unique constraint uq_application_user_job(user_id, job_id).
- Họ tên, email và số điện thoại đều bắt buộc. Tự điền từ tài khoản nếu có, cho phép sửa, nhưng chỉ lưu thông tin riêng vào Application và không cập nhật User.
- Thư giới thiệu không bắt buộc, tối đa 5.000 ký tự; kiểm tra độ dài tại backend khi triển khai luồng nộp đơn.
- Candidate chưa có CV được hướng dẫn tới trang Quản lý CV.
- Sau đăng nhập có thể quay lại đúng công việc/form ứng tuyển bằng next nội bộ đã kiểm tra endpoint và vai trò, không tạo open redirect. Không có next hợp lệ thì giữ điều hướng đăng nhập hiện có. apply=1 chỉ mở form, không tự động gửi đơn.
- CV còn được bất kỳ Application nào tham chiếu không được xóa, kể cả đơn đã rút; phải giải thích rõ lý do và giữ nguyên file/lịch sử. Sau khi thay CV, CV cũ chỉ được xóa nếu không còn Application nào tham chiếu.
- REJECTED và WITHDRAWN là hai trạng thái kết thúc cho phép ẩn CV nếu mọi đơn tham chiếu đều đã kết thúc; vẫn không cho xóa CV còn tham chiếu. Luồng ẩn CV phải giữ thứ tự khóa User → CV → Application, đồng bộ với nộp đơn và thay CV.
- Candidate chỉ được thay CV khi Recruiter chưa xem hồ sơ, Application còn SUBMITTED. Không cho thay khi VIEWED, đang xử lý, REJECTED, WITHDRAWN hoặc trạng thái không xác định; CV thay thế phải thuộc Candidate và không bị ẩn.
- Thay CV chỉ cập nhật cv_id của Application hiện tại, không tạo đơn mới. Giữ nguyên applied_at, thông tin liên hệ, thư giới thiệu, trạng thái và các trường khác của đơn.
- Thay CV không yêu cầu Job còn OPEN. CV hiển thị trong chi tiết đơn là CV hiện đang gắn với Application, không tự tạo lịch sử CV cũ.
- Candidate được rút đơn của mình khi trạng thái chính xác SUBMITTED, VIEWED, CONSIDERING hoặc INTERVIEW, kể cả Job đã đóng, hết hạn hoặc bị ẩn. Chặn REJECTED và mọi trạng thái không xác định. Chỉ cập nhật application_status thành WITHDRAWN và withdrawn_at, không xóa đơn hoặc thay dữ liệu khác.
- Rút đơn đã WITHDRAWN là idempotent, giữ nguyên withdrawn_at. Đơn đã rút vẫn chặn ứng tuyển lại cùng Job và giữ ràng buộc bảo vệ CV. Recruiter mở đơn đã rút không ghi đè WITHDRAWN thành VIEWED. Rút đơn khóa User actor/người nhận theo ID tăng dần → CV → Job → Application, kiểm tra lại cv_id và công ty nhận thông báo sau khi khóa để đồng bộ với thay CV, ẩn CV và mở hồ sơ.
- Không cho trạng thái đã xem hoặc xử lý quay lại SUBMITTED. Việc đánh dấu đã xem phải được thực hiện tại backend của luồng Recruiter mở hồ sơ/CV, không dựa vào trạng thái đọc thông báo.
- Job đã từng có Application không được sửa nội dung. Tăng số lượng và gia hạn vẫn theo điều kiện OPEN, còn hạn, không bị ẩn.
- quantity là số lượng cần tuyển, không giới hạn số Application và không bị giảm khi nhận đơn.
- Nộp đơn không tự xác nhận kỹ năng, không đánh dấu CV đã phân tích xong và không thay đổi quy trình CV–JD.
- Recruiter chỉ được xem đơn, thông tin liên hệ, thư giới thiệu và CV thuộc Job của công ty mình. Đợt 2B đã triển khai xem xét/từ chối theo bảng chuyển trạng thái, chưa triển khai mời phỏng vấn hoặc tính điểm CV–JD.
- Đợt 2C đã triển khai thông báo website cho lần chuyển SUBMITTED → VIEWED thành công, đúng một lần cho mỗi Application. Đọc thông báo hoặc GET hồ sơ không thay thế thao tác mở hồ sơ/CV có CSRF và không tự ghi nhận VIEWED.
- Recruiter vẫn được xem CV đã nộp qua Application thuộc Job của công ty mình, kể cả khi Candidate ẩn CV sau khi đơn kết thúc. Không dùng bộ lọc CV được phép chọn để chặn truy cập hồ sơ đã nộp.
- Card /jobs hiển thị gọn với logo trái, tên công việc/công ty ở giữa và lương bên phải. Xem nhanh là pill ở khu vực trên, chỉ hiện khi hover/focus-within trên desktop và luôn thao tác được trên cảm ứng. Hàng dưới gồm Xem chi tiết, Ứng tuyển và Lưu tin (trái tim 32px, màu xanh #2563A6 ở cả hai trạng thái). Kinh nghiệm lưu dạng ngắn như "4 năm", "1–2 năm", "Dưới 1 năm", "Không yêu cầu". Card/header hiển thị "Kinh nghiệm: 4 năm"; khu vực đã có nhãn Kinh nghiệm chỉ hiển thị "4 năm". Không tự thêm hậu tố hoặc ghi lại dữ liệu khi xem. Tên công việc và liên kết trong Quick View dẫn tới chi tiết. Một Quick View Modal dùng chung, chỉ đọc dữ liệu tin công khai, giữ bộ lọc/phân trang/vị trí cuộn và hiển thị JD như văn bản để tránh XSS.
- Danh sách, Quick View, trang chi tiết và danh sách đã lưu dùng chung Apply Modal, đọc CV thuộc Candidate đang hiển thị và thông tin tài khoản qua application-options. Chỉ nộp vào endpoint candidate.apply_job hiện có, kiểm tra lại điều kiện tại lúc lưu. Không lồng form POST vào form tìm kiếm GET, không upload CV trực tiếp.
- Trạng thái đã ứng tuyển phải phản ánh mọi Application trong lịch sử, kể cả WITHDRAWN. Lỗi lưu đơn không được tự coi là đã ứng tuyển. Trạng thái lưu chỉ thay đổi trên giao diện sau phản hồi backend và phải nhất quán khi tải lại các trang.
- Không thêm cascade xóa Application theo User, CV hoặc Job. Migration phải kiểm tra dữ liệu cũ trước DDL, không tự xóa, gộp hoặc tạo thông tin giả.

### Công ty công khai
- GET /companies/<company_id> hiển thị hồ sơ công ty cho Guest và các vai trò, không yêu cầu đăng nhập. Chỉ đưa tên, logo, giới thiệu, địa chỉ và website hợp lệ ra View, không công khai dữ liệu tài khoản Recruiter. Không suy diễn quy mô, ngành nghề, ngày thành lập, tọa độ hoặc thông tin theo dõi/đánh giá.
- Danh sách và tổng số tin của công ty phải dùng visible_jobs(): OPEN, không bị ẩn và deadline từ hôm nay trở đi. Lọc trước khi đếm và phân trang, không để lộ tin ẩn, đóng, hết hạn hoặc tin của công ty khác.
- Công ty không có tin công khai vẫn hiển thị hồ sơ cùng trạng thái danh sách rỗng. Công ty không tồn tại hoặc ID ngoài miền INT dương trả 404. Hồ sơ chỉ đọc, không thay đổi Company/User/Job/Application/CV.
- Logo và tên công ty trên trang chi tiết việc làm dẫn đến public_companies.show bằng url_for(). Website công ty là liên kết ngoài riêng biệt, kiểm tra bằng company_website_url(), dùng rel="noopener noreferrer".
- Tái sử dụng card, Quick View, Apply Modal và Save/Unsave hiện có. Chuẩn bị card theo người xem qua public_job_service, giữ Cache-Control: private, no-store vì trạng thái thao tác và CSRF phụ thuộc phiên.

### Admin
- Sử dụng layout riêng.
- Bảo toàn chức năng quản lý tài khoản và tin tuyển dụng.
- Không tự ý thay đổi quy tắc khóa/mở khóa hoặc ẩn tin.

### Thông báo tự động — Đợt 2C
- Thông báo lưu trong bảng notifications, kể cả khi người nhận offline hoặc bị khóa. Chỉ Candidate/Recruiter đang hoạt động được truy cập hộp thư thuộc tài khoản của mình. Không có API tạo thông báo từ client hoặc chức năng Admin gửi thủ công.
- Sự kiện: nộp đơn và rút đơn thông báo Recruiter; lần đầu SUBMITTED → VIEWED, chuyển CONSIDERING hoặc REJECTED thông báo Candidate; Admin ẩn/hiện lại Job thông báo Recruiter. Không gửi email cho các thay đổi này, không tạo lại thông báo từ lịch sử trước Đợt 2C.
- Tạo Notification trong transaction nghiệp vụ, không commit riêng. Sự kiện Application có event_key ổn định và UNIQUE uq_notification_user_event(user_id, event_key). Admin đặt is_hidden tường minh dưới khóa; mỗi lần thực sự đổi trạng thái có một event_key riêng. No-op, request lặp không đổi trạng thái hoặc rollback không được tạo thông báo.
- Khóa User actor/người nhận theo ID tăng dần trước CV/Job/Application, actor khóa độc quyền và người nhận khóa chia sẻ. Thay CV, ẩn/hiện CV và xóa CV giữ quy tắc đã chốt. Không thêm cascade xóa dữ liệu.
- Chuông dùng chung Candidate/Recruiter, hiển thị số chưa đọc và tám thông báo mới nhất. /notifications có lọc Tất cả/Chưa đọc/Đã đọc và phân trang. POST đánh dấu từng thông báo, tất cả hoặc mở thông báo phải có CSRF và kiểm tra ownership. Mở dropdown không đánh dấu đã đọc; bấm thông báo kiểm tra lại quyền rồi điều hướng nội bộ.
- Đánh dấu tất cả khóa User trước khi cập nhật toàn bộ thông báo hiện có của tài khoản. Thông báo được tạo sau điểm xử lý này vẫn chưa đọc. Đọc thông báo không thay đổi Application.
- Polling sau mỗi 5 giây khi tab hoạt động, dùng timer sau khi request hoàn tất, không gửi chồng request và không tải lại toàn trang. Tạm dừng khi tab ẩn, đồng bộ ngay khi trở lại hoặc mạng kết nối lại; lỗi dùng backoff. BroadcastChannel chỉ truyền tín hiệu đồng bộ, không truyền CV/thông tin liên hệ. Logout, đổi tài khoản hoặc khóa tài khoản phải dừng polling và che nội dung riêng tư.
- API sync chỉ đọc dữ liệu cần thiết, giới hạn tám thông báo và tối đa 50 Application thuộc quyền. Dùng trạng thái Application/Job hiện tại, không suy diễn trạng thái từ thông báo cũ. Candidate không nhận tiêu đề/công ty/liên kết công khai khi Job bị Admin ẩn. Thông báo LEGACY dùng nội dung chung an toàn, không hiển thị message tự do có thể chứa dữ liệu cũ.
- API polling dùng một query cho tài khoản/hộp thư, tối đa hai query khi theo dõi Application/thống kê. Giữ index theo tài khoản để MySQL không quét ngược PRIMARY qua thông báo của người khác. Khi sửa polling phải đo cả độ trễ API, query count, CPU và ảnh hưởng trang khác, không chỉ kiểm tra chức năng.
- Migration d84e2f6a7b30 nối sau b73d8a4c9f10, bổ sung event_type, event_key, job_id, FK, UNIQUE và index. Bản ghi cũ chỉ bổ sung metadata LEGACY, không backfill sự kiện nghiệp vụ. MySQL chính chỉ được áp dụng sau backup và phê duyệt riêng; không khởi động mã mới với schema chưa tương thích.

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
- Trang chi tiết việc làm công khai giữ bố cục hai cột trên desktop, một cột trên mobile. Header gọn nhưng đủ thông tin và thao tác ứng tuyển/lưu tin. Tiêu đề mục khoảng 18px, màu #183B63, cách nội dung 8–10px. Toàn bộ văn bản mô tả/tổng quan/yêu cầu/quyền lợi ở cột trái màu #212529. Kỹ năng bắt buộc và ưu tiên nằm sau Quyền lợi. Bỏ mục không có nội dung thực tế và tránh chèn dòng trống từ HTML vào khối pre-line. Kinh nghiệm ở card và chi tiết hiển thị trực tiếp giá trị ngắn, có nhãn Kinh nghiệm và fallback "Chưa cập nhật" khi thiếu dữ liệu. Không dùng macro/helper định dạng kinh nghiệm hoặc suy diễn kỹ năng.
- Hồ sơ công ty công khai dùng layout chung: header phía trên, desktop hai cột với Giới thiệu/Tin tuyển dụng bên trái và Thông tin chung/Địa điểm bên phải, mobile một cột. Chỉ hiển thị dữ liệu có thật, dùng trạng thái giải thích khi thông tin tùy chọn chưa được cập nhật.
- Card và modal việc làm tái sử dụng jobs/_job_card.html, jobs/_modals.html, css/jobs.css và js/jobs.js. Chuyển/đóng modal phải chờ đúng vòng đời Bootstrap, kể cả thao tác trong hiệu ứng mở, không để nhiều backdrop hoặc khóa cuộn sau khi đóng. CSS mỗi thuộc tính một dòng, thụt 4 dấu cách mỗi cấp và không lặp selector cùng ngữ cảnh.
- Giao diện đơn ứng tuyển dùng layout Candidate hiện có, có menu active cho danh sách và chi tiết. Card CV hiển thị hai cột từ desktop, một cột trên tablet/mobile, các nút đồng bộ chiều cao. Tách phạm vi CSS danh sách CV khỏi xác nhận kỹ năng; CSS thu gọn việc làm đã lưu chỉ áp dụng trong .jobs-saved-page, không đổi card công khai. Các thao tác Candidate qua JavaScript chỉ cập nhật sau phản hồi thành công của backend, giữ CSRF và hiển thị nguyên nhân khi bị từ chối.
- Hồ sơ Recruiter dùng recruiter_base.html và CSS có phạm vi riêng, tái sử dụng nhãn trạng thái hiện có. Điều hướng từ danh sách Job bằng bộ lọc job_id, không cần sửa recruiter/job_detail.html. Các response hồ sơ/CV phải private, no-store; không đưa đường dẫn file vật lý hoặc URL upload công khai ra View. Form mở hồ sơ HTML dùng POST–redirect–GET, giữ tương thích JSON của API cũ.

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
