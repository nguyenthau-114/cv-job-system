
import re

from app.models.skill import Skill
from app.models.skill_alias import SkillAlias


# Các tiêu đề thường dùng cho danh sách kỹ năng kỹ thuật.
SKILL_HEADINGS = (
    r"programming languages?|programming skills?|"
    r"technical skills?|tech stack|technologies|"
    r"ngôn ngữ lập trình|kỹ năng lập trình|"
    r"kỹ năng chuyên môn|công nghệ sử dụng"
)


def normalize_text(text):
    """Chuẩn hóa văn bản, giữ xuống dòng để kiểm tra ngữ cảnh."""
    text = text.casefold().replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def get_skill_pattern(skill_name):
    """Tạo regex nhận diện kỹ năng độc lập, hỗ trợ Unicode."""
    return r"(?<![\w+#.])" + re.escape(skill_name) + r"(?![\w+#]|\.\w)"


def contains_skill(text, skill_name):
    """Kiểm tra kỹ năng xuất hiện độc lập trong văn bản."""
    if not text or not skill_name:
        return False

    return re.search(
        get_skill_pattern(normalize_text(skill_name)),
        normalize_text(text),
        re.IGNORECASE
    ) is not None


def is_spaced_heading(text, start, end):
    """Phát hiện tiêu đề viết cách từng ký tự."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)

    if line_end == -1:
        line_end = len(text)

    line = text[line_start:line_end].strip()
    return bool(re.fullmatch(r"[a-z](?:[ \t]+[a-z]){3,}", line))


def get_line_context(text, start, end):
    """Lấy nội dung dòng chứa kỹ năng và dòng liền trước."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)

    if line_end == -1:
        line_end = len(text)

    line = text[line_start:line_end]
    before = line[:start - line_start]
    after = line[end - line_start:]

    previous_text = text[:line_start].rstrip("\n")
    previous_line = previous_text.split("\n")[-1].strip() if previous_text else ""

    return before, after, previous_line


def has_programming_context(text, start, end, known_names):
    """Kiểm tra ngữ cảnh kỹ thuật dựa trên cấu trúc và dữ liệu MySQL."""
    before, after, previous_line = get_line_context(text, start, end)

    # Danh sách có tiêu đề kỹ thuật trên cùng dòng.
    if re.search(
        rf"(?:{SKILL_HEADINGS})[ \t]*[:：][ \t]*.*$",
        before
    ):
        return True

    # Danh sách có tiêu đề kỹ thuật ở dòng trước.
    if re.fullmatch(
        rf"(?:{SKILL_HEADINGS})[ \t]*[:：]?",
        previous_line
    ):
        return True

    # Tìm kỹ năng đứng cạnh trong danh sách có dấu phân cách.
    left = re.search(r"([^,;/|&]+)[ \t]*[,;/|&][ \t]*$", before)
    right = re.match(r"[ \t]*[,;/|&][ \t]*([^,;/|&]+)", after)

    neighbors = []

    if left:
        neighbors.append(left.group(1).strip())

    if right:
        neighbors.append(right.group(1).strip())

    # Chỉ dùng tên kỹ năng đủ dài làm bằng chứng ngữ cảnh.
    for neighbor in neighbors:
        if neighbor in known_names and len(neighbor) > 2:
            return True

    return False


def is_valid_ambiguous_skill(text, match, skill_name, known_names):
    """Kiểm tra ngữ cảnh chung cho kỹ năng ngắn dễ nhập nhằng."""
    if len(skill_name) > 2 or any(char in skill_name for char in "+#._"):
        return True

    start, end = match.span()

    # Loại ký tự trong tiêu đề viết cách từng chữ.
    if is_spaced_heading(text, start, end):
        return False

    # Kiểm tra mô tả kỹ thuật ngay sau tên kỹ năng.
    after = text[end:end + 60]

    if re.match(
        r"[ \t]+(?:programming(?:[ \t]+language)?|language)\b",
        after
    ):
        return True

    # Kiểm tra danh sách kỹ năng dựa trên cấu trúc văn bản.
    return has_programming_context(text, start, end, known_names)

def extract_skills(text):
    """Trích xuất kỹ năng bằng Exact Matching, Alias và kiểm tra ngữ cảnh."""
    if not text or not text.strip():
        return []

    normalized_text = normalize_text(text)

    # Lấy danh mục kỹ năng đang hoạt động từ MySQL.
    skills = Skill.query.filter_by(skill_status="ACTIVE").all()
    aliases = SkillAlias.query.all()

    skill_names = {}

    for skill in skills:
        skill_names[skill.skill_id] = {
            "skill_name": skill.skill_name,
            "names": [skill.skill_name]
        }

    # Gom alias vào kỹ năng tương ứng.
    for alias in aliases:
        if alias.skill_id in skill_names:
            skill_names[alias.skill_id]["names"].append(alias.alias_name)

    candidates = []

    for skill_id, data in skill_names.items():
        for name in data["names"]:
            normalized_name = normalize_text(name)

            if normalized_name:
                candidates.append({
                    "skill_id": skill_id,
                    "skill_name": data["skill_name"],
                    "extracted_name": name,
                    "normalized_name": normalized_name
                })

    # Tập tên kỹ năng và alias lấy từ MySQL.
    known_names = {candidate["normalized_name"] for candidate in candidates}

    # Ưu tiên kỹ năng dài hơn để tránh nhận diện chồng lấn.
    candidates.sort(
        key=lambda item: len(item["normalized_name"]),
        reverse=True
    )

    detected_skills = []
    detected_ids = set()
    matched_positions = []

    for candidate in candidates:
        if candidate["skill_id"] in detected_ids:
            continue

        name = candidate["normalized_name"]
        pattern = get_skill_pattern(name)

        for match in re.finditer(pattern, normalized_text, re.IGNORECASE):
            # Kiểm tra ngữ cảnh với tên kỹ năng dễ nhập nhằng.
            if not is_valid_ambiguous_skill(
                normalized_text, match, name, known_names
            ):
                continue

            start, end = match.span()

            # Bỏ qua vị trí trùng với kỹ năng dài hơn đã nhận diện.
            overlapping = any(
                start < used_end and end > used_start
                for used_start, used_end in matched_positions
            )

            if overlapping:
                continue

            detected_skills.append({
                "skill_id": candidate["skill_id"],
                "skill_name": candidate["skill_name"],
                "extracted_name": candidate["extracted_name"]
            })

            detected_ids.add(candidate["skill_id"])
            matched_positions.append((start, end))
            break

    return detected_skills
