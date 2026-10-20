# Import các Model để SQLAlchemy/Migration nhận diện được các bảng
from app.models.user import User
from app.models.company import Company
from app.models.cv import CV
from app.models.skill import Skill
from app.models.skill_alias import SkillAlias
from app.models.candidate_skill import CandidateSkill
from app.models.job_category import JobCategory
from app.models.job import Job
from app.models.job_skill import JobSkill
from app.models.application import Application
from app.models.saved_job import SavedJob
from app.models.interview_invitation import InterviewInvitation
from app.models.notification import Notification