from app import create_app
from app.extensions import db
from app.models.skill import Skill
from app.models.skill_alias import SkillAlias

# Alias chỉ dành cho tên tương đương; không dùng từ viết tắt dễ gây nhầm.
SKILL_ALIASES = {
    'JavaScript': ['JS'],
    'React': ['ReactJS', 'React.js'],
    'Next.js': ['NextJS'],
    'Vue.js': ['VueJS'],
    'AngularJS': ['Angular.js', 'Angular 1.x'],
    'Tailwind CSS': ['Tailwind', 'TailwindCSS'],
    'Node.js': ['NodeJS'],
    'Express.js': ['ExpressJS'],
    'NestJS': ['Nest.js'],
    'Spring Boot': ['SpringBoot'],
    'ASP.NET Core': ['ASP.NETCore'],
    '.NET Core': ['Dotnet Core', 'DotNetCore'],
    '.NET MAUI': ['NET MAUI', 'Dotnet MAUI'],
    'Entity Framework': ['EntityFramework'],
    'PostgreSQL': ['Postgres', 'Postgre SQL'],
    'Microsoft SQL Server': ['SQL Server', 'SQLServer', 'MSSQL'],
    'Oracle Database': ['Oracle DB'],
    'Elasticsearch': ['Elastic Search'],
    'REST API': ['RESTful API', 'RESTful APIs', 'RESTful Web Services'],
    'Microservices': ['Microservice'],
    'WebSocket': ['WebSockets'],
    'OOP': ['Object-Oriented Programming'],
    'MVC': ['Model View Controller', 'Model-View-Controller'],
    'MVVM': ['Model View ViewModel', 'Model-View-ViewModel'],
    'OAuth 2.0': ['OAuth2', 'OAuth 2'],
    'Scikit-learn': ['Scikit Learn', 'Sklearn'],
    'TensorFlow': ['Tensor Flow'],
    'Natural Language Processing': ['NLP'],
    'Selenium': ['Selenium WebDriver'],
    'Automation Testing': ['Automated Testing'],
    'Kubernetes': ['K8s'],
    'Amazon Web Services': ['AWS'],
    'Microsoft Azure': ['Azure', 'Azure Cloud'],
    'Google Cloud Platform': ['GCP', 'Google Cloud'],
    'GitLab CI/CD': ['GitLab CI'],
    'Windows Server': ['Windows Server OS'],
    'Penetration Testing': ['Pentest', 'Pen Testing'],
    'IBM QRadar': ['QRadar'],
    'Vulnerability Assessment': ['Vulnerability Testing'],
    'Apache Kafka': ['Kafka'],
    'Adobe Photoshop': ['Photoshop'],
    'Adobe Illustrator': ['Illustrator'],
    'Swagger': ['OpenAPI'],
    'SOAP API': ['SOAP Web Services'],
    'ETL': ['Extract Transform Load', 'Extract, Transform, Load'],
    'Data Warehousing': ['Data Warehouse'],
    'Apache Airflow': ['Airflow'],
    'Google BigQuery': ['BigQuery'],
    'Playwright': ['Microsoft Playwright'],
    'API Testing': ['API Test', 'Kiểm thử API'],
    'Integration Testing': ['Integration Test'],
    'Performance Testing': ['Performance Test', 'Load Testing'],
    'Regression Testing': ['Regression Test'],
    'CI/CD': ['Continuous Integration and Continuous Delivery', 'Continuous Integration/Continuous Deployment'],
    'Windows': ['Microsoft Windows'],
    'macOS': ['Mac OS', 'Mac OS X'],
    'Microsoft 365': ['Office 365', 'M365', 'Microsoft Office 365'],
    'Microsoft SharePoint': ['SharePoint', 'SharePoint Online'],
    'DHCP': ['Dynamic Host Configuration Protocol'],
    'VPN': ['Virtual Private Network'],
    'LAN/WAN': ['LAN and WAN'],
    'VoIP': ['Voice over IP', 'Voice over Internet Protocol'],
    'Hardware Troubleshooting': ['Hardware Troubleshooting and Repair'],
    'Technical Support': ['IT Support', 'IT Helpdesk', 'Help Desk Support'],
    'IDS/IPS': ['Intrusion Detection System', 'Intrusion Prevention System'],
    'Incident Response': ['Security Incident Response'],
    'EDR': ['Endpoint Detection and Response'],
    'Business Analysis': ['Business Analyst Skills', 'Phân tích nghiệp vụ'],
    'UML': ['Unified Modeling Language'],
    'BPMN': ['Business Process Model and Notation', 'BPMN 2.0'],
    'Requirements Gathering': ['Requirement Elicitation', 'Requirements Elicitation'],
    'User Stories': ['User Story Writing'],
    'UAT': ['User Acceptance Testing'],
    'User Research': ['UX Research'],
    'Active Directory': ['Microsoft Active Directory'],
    'SQL': ['Structured Query Language'],
}

OBSOLETE_ALIASES = {'AngularJS': 'Angular', '.NET Core': 'ASP.NET Core', 'ASP.NET': 'ASP.NET Core', 'Nest': 'NestJS', 'CV': 'Computer Vision', 'AD': 'Active Directory'}

def main():
    app = create_app()
    with app.app_context():
        try:
            skills = {s.skill_name: s for s in Skill.query.all()}
            missing = sorted(set(SKILL_ALIASES) - set(skills))
            if missing:
                raise ValueError("Run seed_skills.py first. Missing: " + ", ".join(missing))
            removed = 0
            for alias_name, old_name in OBSOLETE_ALIASES.items():
                old_skill = skills.get(old_name)
                if old_skill is None:
                    continue
                for record in SkillAlias.query.filter_by(alias_name=alias_name, skill_id=old_skill.skill_id).all():
                    db.session.delete(record)
                    removed += 1
            db.session.flush()
            added = 0
            conflicts = []
            existing = {a.alias_name.casefold(): a for a in SkillAlias.query.all()}
            canonical = {name.casefold(): name for name in skills}
            for skill_name, names in SKILL_ALIASES.items():
                skill = skills[skill_name]
                for name in names:
                    key = name.casefold()
                    if key in canonical:
                        continue
                    record = existing.get(key)
                    if record is None:
                        record = SkillAlias(skill_id=skill.skill_id, alias_name=name)
                        db.session.add(record)
                        existing[key] = record
                        added += 1
                    elif record.skill_id != skill.skill_id:
                        # Không tự chuyển alias đang thuộc kỹ năng khác.
                        conflicts.append((name, skill_name))
            db.session.commit()
            print(f"Seed aliases OK: {added} added, {removed} obsolete removed")
            if conflicts:
                print("Review alias conflicts manually:", conflicts)
        except Exception:
            db.session.rollback()
            raise

if __name__ == "__main__":
    main()
