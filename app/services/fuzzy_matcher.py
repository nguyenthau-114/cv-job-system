import re
from rapidfuzz import fuzz, process

# Không fuzzy các kỹ năng ngắn hoặc dễ gây nhầm lẫn.
MIN_SKILL_LENGTH = 5
FUZZY_THRESHOLD = 90


def normalize_skill_name(name):
    """Chuẩn hóa tên kỹ năng để so sánh."""
    name = name.casefold().strip()
    return re.sub(r"\s+", " ", name)


def fuzzy_match_skill(text, skill_names, threshold=FUZZY_THRESHOLD):
    """Tìm kỹ năng gần giống nhất trong danh mục."""
    text = normalize_skill_name(text)

    if len(text) < MIN_SKILL_LENGTH:
        return None

    # Chỉ xét tên kỹ năng đủ dài.
    choices = {
        normalize_skill_name(name): name
        for name in skill_names
        if len(normalize_skill_name(name)) >= MIN_SKILL_LENGTH
    }

    if not choices:
        return None

    result = process.extractOne(
        text,
        list(choices.keys()),
        scorer=fuzz.ratio,
        score_cutoff=threshold
    )

    if result is None:
        return None

    matched_name, score, _ = result

    return {
        "input": text,
        "matched_skill": choices[matched_name],
        "score": round(score, 2)
    }
SKILL_SECTION_HEADINGS = (
    r"technical skills?|programming languages?|programming skills?|"
    r"tech stack|technologies|frameworks?|tools?|"
    r"kỹ năng chuyên môn|kỹ năng kỹ thuật|"
    r"ngôn ngữ lập trình|công nghệ sử dụng"
)

SECTION_END_HEADINGS = (
    r"summary|professional summary|profile|about me|"
    r"career objective|objective|personal information|"
    r"education|academic background|qualifications?|"
    r"experience|work experience|employment history|"
    r"professional experience|projects?|personal projects?|"
    r"certifications?|achievements?|awards?|languages?|"
    r"interests?|hobbies|references?|contact|"
    r"tóm tắt|giới thiệu bản thân|thông tin cá nhân|"
    r"mục tiêu nghề nghiệp|học vấn|trình độ học vấn|"
    r"kinh nghiệm|kinh nghiệm làm việc|dự án|"
    r"chứng chỉ|thành tích|giải thưởng|ngoại ngữ|"
    r"sở thích|người tham chiếu|liên hệ"
)


def extract_skill_phrases(text):
    """Lấy các cụm trong danh sách kỹ năng có tiêu đề rõ ràng."""
    if not text:
        return []

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    phrases = []
    in_skill_section = False

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # Tiêu đề kỹ năng và nội dung trên cùng dòng.
        heading_match = re.match(
            rf"^(?:{SKILL_SECTION_HEADINGS})\s*[:：]\s*(.*)$",
            line,
            re.IGNORECASE
        )

        if heading_match:
            in_skill_section = True
            line = heading_match.group(1).strip()

        # Tiêu đề kỹ năng nằm trên một dòng riêng.
        elif re.fullmatch(
            rf"(?:{SKILL_SECTION_HEADINGS})\s*[:：]?",
            line,
            re.IGNORECASE
        ):
            in_skill_section = True
            continue

        elif in_skill_section:
            # Gặp tiêu đề phần khác thì dừng.
            if re.fullmatch(
                rf"(?:{SECTION_END_HEADINGS})\s*[:：]?",
                line,
                re.IGNORECASE
            ):
                in_skill_section = False
                continue

        if not in_skill_section:
            continue

        # Tách các mục kỹ năng theo dấu phân cách rõ ràng.
        line = re.sub(r"^[•●▪\-*]\s*", "", line)
        parts = re.split(r"[,;|]", line)

        for part in parts:
            phrase = part.strip(" \t•●▪-*")

            # Loại cụm quá ngắn hoặc quá dài.
            if 3 <= len(phrase) <= 40 and len(phrase.split()) <= 5:
                phrases.append(phrase)

    return list(dict.fromkeys(phrases))

def extract_fuzzy_skills(text, skill_names, exact_names=None):
    """Gợi ý kỹ năng gần giống, không tự động xác nhận."""
    phrases = extract_skill_phrases(text)
    exact_names = {
        normalize_skill_name(name)
        for name in (exact_names or [])
    }

    results = []
    suggested_names = set()

    for phrase in phrases:
        normalized_phrase = normalize_skill_name(phrase)

        # Bỏ qua cụm đã có trong danh mục hoặc alias.
        if normalized_phrase in exact_names:
            continue

        match = fuzzy_match_skill(phrase, skill_names)

        if match is None:
            continue

        # Khớp 100% phải được xử lý bằng Exact Matching.
        if match["score"] == 100:
            continue

        matched_name = match["matched_skill"]
        normalized_name = normalize_skill_name(matched_name)

        # Không gợi ý kỹ năng đã nhận diện hoặc đã gợi ý.
        if normalized_name in exact_names or normalized_name in suggested_names:
            continue

        suggested_names.add(normalized_name)

        results.append({
            "extracted_name": phrase,
            "matched_skill": matched_name,
            "score": match["score"]
        })

    return results

def extract_fuzzy_skills_db(text, exact_skills=None):
    """Gợi ý kỹ năng từ MySQL, trả về skill_id và tên chuẩn."""
    from app.models.skill import Skill
    from app.models.skill_alias import SkillAlias

    skills = Skill.query.filter_by(skill_status="ACTIVE").all()
    aliases = SkillAlias.query.all()

    skill_map = {}
    choices = []

    for skill in skills:
        skill_map[skill.skill_id] = skill.skill_name
        choices.append((skill.skill_name, skill.skill_id))

    for alias in aliases:
        if alias.skill_id in skill_map:
            choices.append((alias.alias_name, alias.skill_id))

    # Loại kỹ năng đã được Exact Matching hoặc Alias nhận diện.
    exact_ids = {
        item["skill_id"] for item in (exact_skills or [])
    }

    results = []
    suggested_ids = set()

    for phrase in extract_skill_phrases(text):
        # Ưu tiên nhận diện chính xác, kể cả alias.
        normalized_phrase = normalize_skill_name(phrase)
        if any(
            normalize_skill_name(name) == normalized_phrase
            for name, _ in choices
        ):
            continue

        match = fuzzy_match_skill(
            phrase,
            [name for name, _ in choices]
        )

        if match is None or match["score"] == 100:
            continue

        matched_name = normalize_skill_name(match["matched_skill"])

        for name, skill_id in choices:
            if normalize_skill_name(name) != matched_name:
                continue

            if skill_id in exact_ids or skill_id in suggested_ids:
                break

            results.append({
                "skill_id": skill_id,
                "skill_name": skill_map[skill_id],
                "extracted_name": phrase,
                "matched_name": name,
                "score": match["score"]
            })

            suggested_ids.add(skill_id)
            break

    return results

def get_fuzzy_context(text, extracted_name):
    """Tìm dòng văn bản gốc chứa cụm được Fuzzy đề xuất."""
    if not text or not extracted_name:
        return ""

    normalized_name = normalize_skill_name(extracted_name)

    for line in text.splitlines():
        if normalized_name in normalize_skill_name(line):
            return line.strip()[:300]

    return ""