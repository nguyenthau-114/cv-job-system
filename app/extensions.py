from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail

# Quản lý kết nối và thao tác database bằng SQLAlchemy
db = SQLAlchemy()

# Quản lý các thay đổi cấu trúc database (migration)
migrate = Migrate()

# Bảo vệ các form POST khỏi tấn công CSRF
csrf = CSRFProtect()

# Quản lý việc gửi email từ hệ thống
mail = Mail()