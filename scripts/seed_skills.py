from app import create_app
from app.extensions import db
from app.models.skill import Skill


# =========================================================
# DANH MỤC KỸ NĂNG CNTT CHUẨN CỦA JOBFIT
# Các nhóm bên dưới chỉ dùng để code dễ đọc.
# Khi lưu xuống MySQL, tất cả đều nằm trong bảng "skills".
# =========================================================

SKILLS = [

    # 1. Ngôn ngữ lập trình
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "PHP",
    "C",
    "C++",
    "C#",
    "Go",
    "Kotlin",
    "Swift",
    "Dart",
    "R",
    "Ruby",
    "Scala",

    # 2. Frontend
    "HTML",
    "CSS",
    "React",
    "Next.js",
    "Vue.js",
    "Angular",
    "Bootstrap",
    "Tailwind CSS",
    "Redux",
    "jQuery",
    "Sass",

    # 3. Backend / Web Framework
    "Flask",
    "Django",
    "FastAPI",
    "Laravel",
    "Spring Boot",
    "Node.js",
    "Express.js",
    "NestJS",
    "ASP.NET Core",

    # 4. Mobile
    "Android",
    "iOS",
    "Flutter",
    "React Native",

    # 5. Database
    "MySQL",
    "PostgreSQL",
    "Microsoft SQL Server",
    "Oracle Database",
    "MongoDB",
    "Redis",
    "SQLite",
    "Cassandra",
    "Elasticsearch",

    # 6. API / kiến trúc hệ thống
    "REST API",
    "GraphQL",
    "gRPC",
    "Microservices",
    "WebSocket",

    # 7. Data / AI / Machine Learning
    "Pandas",
    "NumPy",
    "Scikit-learn",
    "TensorFlow",
    "PyTorch",
    "Keras",
    "Machine Learning",
    "Deep Learning",
    "Natural Language Processing",
    "Computer Vision",
    "Apache Spark",
    "Hadoop",
    "Power BI",
    "Tableau",

    # 8. Testing / QA
    "Selenium",
    "Cypress",
    "Appium",
    "Katalon",
    "Postman",
    "JMeter",
    "JUnit",
    "Mockito",
    "Pytest",
    "Unit Testing",
    "Automation Testing",
    "Manual Testing",

    # 9. DevOps / Cloud
    "Docker",
    "Kubernetes",
    "Jenkins",
    "GitHub Actions",
    "GitLab CI/CD",
    "Terraform",
    "Ansible",
    "Amazon Web Services",
    "Microsoft Azure",
    "Google Cloud Platform",
    "Nginx",
    "Prometheus",
    "Grafana",

    # 10. Hệ điều hành / hạ tầng / mạng
    "Linux",
    "Windows Server",
    "VMware",
    "TCP/IP",
    "DNS",
    "Active Directory",

    # 11. Cybersecurity
    "Cybersecurity",
    "Network Security",
    "Web Security",
    "Penetration Testing",
    "SIEM",
    "Splunk",
    "IBM QRadar",
    "Firewall",
    "OWASP",
    "Vulnerability Assessment",

    # 12. Message Queue / hệ thống phân tán
    "Apache Kafka",
    "RabbitMQ",

    # 13. Version Control / công cụ phát triển
    "Git",
    "GitHub",
    "GitLab",
    "Bitbucket",
    "Jira",
    "SonarQube",
    "Maven",
    "Gradle",

    # 14. UI/UX
    "Figma",
    "Adobe XD",
    "Adobe Photoshop",
    "Adobe Illustrator",
    "Wireframing",
    "Prototyping",

    # 15. Phương pháp / quản lý dự án phần mềm
    "Agile",
    "Scrum",

    # 16. Framework / Công nghệ
    "Spring Framework",
    "Spring MVC",
    "Spring Security",
    "Spring Data JPA",
    "Hibernate",
    "JPA",
    "Entity Framework",
    ".NET Core",
    ".NET MAUI",
    "ASP.NET MVC",
    "AngularJS",

    # 17. Kiến thức và kỹ thuật lập trình
    "SQL",
    "OOP",
    "MVC",
    "MVVM",
    "SOLID",
    "Design Patterns",
    "LINQ",
    "JWT",
    "OAuth 2.0",

    # 18. Công cụ và thiết kế
    "Excel",
    "Jest",
    "Material UI",
    "Ant Design",
    "Design Systems",
    "User Flows",

    # Bổ sung: Backend / API
    'Swagger',
    'SOAP API',

    # Bổ sung: Data Engineering
    'ETL',
    'Data Warehousing',
    'Apache Airflow',
    'Google BigQuery',

    # Bổ sung: Testing / QA
    'Playwright',
    'API Testing',
    'Integration Testing',
    'Performance Testing',
    'Regression Testing',

    # Bổ sung: DevOps / Cloud
    'CI/CD',

    # Bổ sung: IT Support / Network
    'Windows',
    'macOS',
    'Microsoft 365',
    'Microsoft SharePoint',
    'DHCP',
    'VPN',
    'LAN/WAN',
    'VoIP',
    'Hardware Troubleshooting',
    'Technical Support',

    # Bổ sung: Security
    'IDS/IPS',
    'Incident Response',
    'EDR',

    # Bổ sung: Business Analysis
    'Business Analysis',
    'UML',
    'BPMN',
    'Requirements Gathering',
    'User Stories',
    'UAT',

    # Bổ sung: UI/UX
    'User Research',

]

# Chỉ thêm mới; không xóa, đổi tên hoặc thay ID kỹ năng đang được tham chiếu.
def main():
    app = create_app()
    with app.app_context():
        try:
            existing = {s.skill_name.casefold() for s in Skill.query.all()}
            added = 0
            for name in SKILLS:
                if name.casefold() not in existing:
                    db.session.add(Skill(skill_name=name, skill_status="ACTIVE"))
                    existing.add(name.casefold())
                    added += 1
            db.session.commit()
            print(f"Seed skills OK: {len(SKILLS)} declared, {added} added")
        except Exception:
            db.session.rollback()
            raise

if __name__ == "__main__":
    main()
