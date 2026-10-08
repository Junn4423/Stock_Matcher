from __future__ import annotations

import re
import unicodedata
from collections import Counter

from app.models import QueryPlan, Segment


_WORD_RE = re.compile(r"[\wÀ-ỹ]+(?:[-'][\wÀ-ỹ]+)?", flags=re.UNICODE)
_VI_SIGNAL_QUERY = re.compile(r"[ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ]", re.I)

_VI_STOPWORDS = {
    "và", "là", "của", "có", "cho", "trong", "một", "những", "các", "được", "với",
    "khi", "để", "này", "đó", "từ", "về", "sẽ", "đang", "đã", "rằng", "thì", "mà",
    "như", "không", "nên", "nếu", "bởi", "do", "tại", "trên", "dưới", "ra", "vào",
    "lại", "hơn", "rất", "cũng", "chúng", "tôi", "bạn", "anh", "em", "người", "nhiều",
    "thể", "việc", "đây", "nào", "cần", "giúp", "mới", "đến", "sau", "trước", "giữa",
    "thay", "phải", "tuy", "nhiên", "lĩnh", "vực", "thuộc", "biết", "dùng", "xem",
    "đưa", "cách", "yếu", "tố", "duy", "nhất", "họ", "dành", "rõ", "ràng", "bao",
    "giờ", "tự", "hỏi", "thực", "sự", "gì", "hay", "vì", "thế", "nữa", "dường", "mọi", "mỗi",
}

_EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "for", "in", "on", "at", "by",
    "with", "from", "this", "that", "these", "those", "is", "are", "was", "were", "be",
    "been", "being", "it", "its", "as", "if", "then", "than", "so", "we", "you", "they",
    "he", "she", "i", "our", "your", "their", "can", "could", "should", "would", "will",
    "may", "might", "do", "does", "did", "have", "has", "had", "not", "more", "most",
}

_THEME_ANCHORS = {
    "fitness": "gym workout fitness",
    "history": "history museum ancient",
    "food": "food cooking chef",
    "travel": "travel destination scenery",
    "real_estate": "real estate architecture interior",
    "automotive": "sports car driving vehicle",
    "space": "space galaxy astronomy",
    "healthcare": "doctor hospital healthcare",
    "technology": "technology computer software",
    "business": "business corporate office",
    "finance": "finance stock market money",
    "nature_wildlife": "nature wildlife animals forest",
    "education": "students education university",
    "gaming": "gaming esports streamer",
    "fashion_beauty": "fashion beauty model",
    "general": "cinematic storytelling lifestyle",
}

_PHRASE_MAP = {
    # Fitness & Gym Specific Phrases
    "phòng gym": "gym workout fitness training center",
    "bước vào phòng gym": "person entering modern gym fitness training",
    "hình thể vạm vẹo": "muscular athletic fit body workout exercise",
    "vóc dáng thon gọn": "fit slim body exercise workout gym",
    "cảm giác chiến thắng": "athlete celebrating victory accomplishment gym workout",
    "đốt cháy vài trăm calo": "intense cardio workout burning calories gym",
    "sửa sang lại ngoại hình": "fit body transformation exercise gym",
    "tạ nặng": "heavy weightlifting barbell dumbbell workout",
    "rèn luyện cơ bắp": "muscle building weightlifting exercise gym",
    "mài dũa cả tâm trí": "mental focus discipline athletic workout gym",
    "mức tạ": "heavy weightlifting barbell gym exercise",
    "hơi thở dồn dập": "intense cardio workout breathing heavy athlete",
    "đòi bỏ cuộc": "athlete struggling intense workout exhaustion gym",
    "cuộc chiến thực sự": "intense athletic challenge training struggle gym",
    "vượt qua nó": "athlete overcoming limits heavy weightlifting gym",
    "nâng tầm giới hạn": "athlete pushing limits heavy workout gym",
    "phòng tập": "modern gym workout fitness training center",
    "đĩa tạ": "weight plates barbell gym exercise",
    "ra ngoài cuộc sống": "active healthy lifestyle person outside gym",
    "từng buổi tập": "consistent daily gym workout training discipline",
    "áp lực dưới thanh đòn": "heavy bench press barbell squad weightlifting",
    "sóng gió đời thường": "resilient person facing challenge strong mindset",
    "làm chủ được cơ thể": "confident athlete body control workout posing",
    "tư thế hoàn toàn khác": "confident fit posture person walking gym",
    "cuộc đua": "fitness competition workout race athlete",
    "bản cam kết": "dedication commitment goal fitness workout",
    "phiên bản tốt hơn": "self improvement growth fit person gym",
    "mồ hôi rơi": "sweating athlete intense workout gym training",
    "tự do về sức khỏe": "healthy fit person enjoying freedom active life",
    "vững vàng trong tâm trí": "strong focused mindset athletic person gym",
    "hoàn thành bài tập": "athlete completing workout gym celebration",
    "bài tập yêu thích": "favorite gym exercise weightlifting workout",
    "nạp năng lượng tích cực": "positive energy inspiration fitness lifestyle",

    # Lịch sử
    "lịch sử thực sự": "ancient history museum artifact reflection",
    "lịch sử việt nam": "ancient Vietnam history heritage architecture",
    "lịch sử thế giới": "world history ancient civilization museum",
    "lịch sử": "ancient history museum artifact display",
    "bảo tàng": "museum exhibition historical artifact display",
    "di tích lịch sử": "ancient monument ruins historical architecture",
    "triều đại phong kiến": "ancient kingdom royal palace architecture",
    "chiến tranh": "historic war battle field documentary",

    # Ẩm thực
    "món ăn": "delicious food meal preparation gourmet plate",
    "ẩm thực": "traditional gourmet food cooking chef",
    "nấu ăn": "chef cooking fresh ingredients kitchen",
    "phở bò": "traditional Vietnamese pho noodle soup bowl",
    "cà phê": "brewing fresh espresso coffee cup bean",

    # Du lịch
    "du lịch": "traveler exploring scenic destination vacation",
    "bãi biển": "tropical white sand beach turquoise ocean aerial",
    "khám phá": "adventurer hiking mountain scenic view",

    # Bất động sản
    "bất động sản": "luxury real estate modern apartment building exterior",
    "chung cư": "modern high rise apartment building skyline",
    "biệt thự": "luxury villa mansion architecture exterior pool",

    # Công nghệ & AI
    "trí tuệ nhân tạo": "artificial intelligence technology digital interface",
    "lập trình viên": "software developer coding computer screen",
    "an ninh mạng": "cybersecurity operations center code",
}

_SINGLE_MAP = {
    # Fitness
    "gym": "gym workout fitness",
    "tạ": "heavy weightlifting barbell",
    "cơ": "muscle building athletic workout",
    "bắp": "muscular athletic body",
    "calo": "calories workout exercise",
    "tập": "person workout gym exercise",
    "đòn": "barbell weightlifting exercise",
    "sức": "athletic strength workout",
    "mồ": "sweating athlete workout",
    "hôi": "sweat workout training",

    # Food
    "phở": "vietnamese noodle soup", "lẩu": "hotpot dining table", "nướng": "bbq grill meat food",
    "cà": "coffee brewing cup", "phê": "coffee bean brewing", "bánh": "bakery cake dessert",

    # Travel & Nature
    "biển": "ocean beach tropical landscape", "núi": "mountain peak sunrise scenic",
    "rừng": "green forest nature trees aerial", "đảo": "tropical island ocean turquoise beach",

    # Automotive & Tech
    "xe": "car driving highway road", "code": "software code computer screen",
    "ai": "artificial intelligence digital",

    # History & Science
    "sử": "history museum ancient artifact", "cổ": "ancient heritage ruins monument",
    "sách": "vintage book reading library", "vũ": "space galaxy universe stars",
}

_VI_KEYWORD_TRANSLATIONS = {
    "gym": "gym workout", "tạ": "weightlifting barbell", "cơ": "muscle",
    "bắp": "muscle fit body", "calo": "calories workout", "tập": "exercise workout",
    "đòn": "barbell lifting", "sức": "strength workout", "phở": "vietnamese pho soup",
    "cà": "coffee cup", "phê": "coffee bean", "biển": "beach ocean",
    "núi": "mountain peak", "rừng": "forest nature", "xe": "car driving",
    "nhà": "house home interior", "đất": "real estate land", "tiền": "money cash",
    "bác": "doctor medical", "bệnh": "hospital patient", "thuốc": "medicine pills",
    "game": "gaming setup rgb", "vũ": "space galaxy",
}

_CATEGORY_HINTS = {
    "fitness": {
        "gym", "phòng gym", "tạ", "cơ bắp", "tập", "thể dục", "giảm cân", "chạy bộ", "bóng đá",
        "yoga", "thể hình", "cơ", "bắp", "calo", "workout", "fitness", "exercise", "weightlifting",
        "mức tạ", "sàn tập", "bài tập",
    },
    "history": {
        "lịch sử", "lịch", "sử", "thời xưa", "quá khứ", "thời cổ", "triều đại", "phong kiến",
        "bảo tàng", "văn minh", "chiến tranh", "di tích", "hiện vật", "khảo cổ", "tổ tiên",
        "văn hóa cổ", "lăng mộ", "triều đình", "kinh đô", "anh hùng",
        "history", "ancient", "museum", "historical", "civilization", "heritage", "past",
    },
    "food": {
        "món ăn", "ẩm thực", "nấu ăn", "đầu bếp", "nhà hàng", "phở", "bánh", "cà phê", "trà",
        "lẩu", "nướng", "hải sản", "gia vị", "ăn uống", "quán ăn", "food", "cooking", "chef",
    },
    "travel": {
        "du lịch", "bãi biển", "nghỉ dưỡng", "máy bay", "khám phá", "núi rừng", "phượt",
        "khách sạn", "đảo", "phong cảnh", "hành trình", "travel", "beach", "vacation", "resort",
    },
    "real_estate": {
        "bất động sản", "chung cư", "biệt thự", "nội thất", "kiến trúc", "nhà đất", "thổ cư",
        "xây dựng", "tòa nhà", "phòng khách", "real estate", "apartment", "interior", "house",
    },
    "automotive": {
        "ô tô", "xe điện", "siêu xe", "lái xe", "xe máy", "động cơ", "giao thông", "đường cao tốc",
        "car", "driving", "automobile", "highway", "supercar",
    },
    "space": {
        "vũ trụ", "hành tinh", "hố đen", "phi hành gia", "thiên văn", "ngôi sao", "tên lửa",
        "ngân hà", "space", "galaxy", "astronomy", "planet", "universe", "astronaut",
    },
    "healthcare": {
        "chăm sóc sức khỏe", "bệnh viện", "bác sĩ", "nha sĩ", "y tế", "thuốc", "bệnh nhân",
        "xét nghiệm", "chẩn đoán", "dược", "healthcare", "doctor", "hospital", "medical",
    },
    "technology": {
        "ai", "api", "code", "phần mềm", "công nghệ", "dữ liệu", "server", "cloud", "robot",
        "blockchain", "internet", "ứng dụng", "máy tính", "phần cứng", "thuật toán",
        "technology", "software", "developer", "cybersecurity",
    },
    "business": {
        "doanh nghiệp", "kinh doanh", "khách hàng", "tăng trưởng", "thị trường", "đầu tư",
        "tài chính", "năng suất", "chiến lược", "công ty", "bán hàng", "doanh thu",
        "business", "startup", "corporate", "office", "executive",
    },
    "finance": {
        "chứng khoán", "tài chính", "ngân hàng", "tiền tệ", "cổ phiếu", "lợi nhuận", "lạm phát",
        "vàng", "tài sản", "đầu tư", "stock market", "finance", "banking", "investment",
    },
    "nature_wildlife": {
        "động vật hoang dã", "thú cưng", "đại dương", "rừng rậm", "môi trường", "thiên nhiên",
        "hổ", "sư tử", "cá mập", "loài bướm", "bảo tồn", "wildlife", "nature", "animals", "ocean",
    },
    "education": {
        "giáo dục", "trường học", "sinh viên", "học sinh", "thư viện", "đại học", "thi cử",
        "bài giảng", "sách", "du học", "education", "students", "classroom", "university",
    },
    "gaming": {
        "game", "esports", "trò chơi điện tử", "streamer", "máy tính chơi game", "tai nghe",
        "gaming", "gamer", "video game", "streamer setup",
    },
}

_FALLBACKS = {
    "fitness": "person workout gym training weightlifting exercise b roll",
    "history": "ancient history museum historical architecture documentary b roll",
    "food": "chef preparing delicious gourmet food cooking kitchen b roll",
    "travel": "scenic tropical beach island travel adventure landscape b roll",
    "real_estate": "luxury modern real estate architecture interior design b roll",
    "automotive": "luxury sports car driving highway road scenic b roll",
    "space": "deep space galaxy stars planetary astronomy nebula b roll",
    "healthcare": "doctor consulting patient modern hospital medical clinic b roll",
    "technology": "modern technology digital interface software b roll",
    "business": "business team working modern corporate office b roll",
    "finance": "global stock market trading financial chart analytics b roll",
    "nature_wildlife": "wildlife animals cinematic green forest ocean nature b roll",
    "education": "students learning modern university library classroom b roll",
    "gaming": "gamer playing video game colorful RGB gaming setup b roll",
    "general": "cinematic document storytelling lifestyle b roll",
}

_MOOD_TERMS = {
    "positive": {"tốt", "thành công", "cơ hội", "tăng trưởng", "hiệu quả", "nhanh", "mạnh", "đột phá", "ngon", "đẹp", "positive", "success", "growth"},
    "negative": {"rủi ro", "thất bại", "nguy hiểm", "khó khăn", "vấn đề", "tấn công", "mất", "bệnh", "lỗi", "negative", "risk", "failure", "problem"},
}


def _compress_query(text: str, max_words: int = 10) -> str:
    words = re.findall(r"[A-Za-z0-9-]+", text.lower())
    result: list[str] = []
    seen: set[str] = set()
    for word in words:
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= max_words:
            break
    return " ".join(result)


def _strip_accents(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFD", text) if unicodedata.category(char) != "Mn"
    ).replace("đ", "d").replace("Đ", "D")


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _WORD_RE.findall(text)]


def _detect_language(text: str) -> str:
    lowered = text.lower()
    vi_chars = sum(1 for ch in lowered if ch in "ăâđêôơưàáạảãằắặẳẵầấậẩẫèéẹẻẽềếệểễìíịỉĩòóọỏõồốộổỗờớợởỡùúụủũừứựửữỳýỵỷỹ")
    vi_words = sum(1 for token in _tokens(lowered) if token in _VI_STOPWORDS)
    return "vi" if vi_chars >= 2 or vi_words >= 2 else "en"


def _phrase_matches(text: str) -> list[tuple[str, str]]:
    lowered = text.lower()
    matches: list[tuple[str, str]] = []
    occupied: list[tuple[int, int]] = []
    for phrase, visual in sorted(_PHRASE_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", lowered):
            span = match.span()
            if any(not (span[1] <= start or span[0] >= end) for start, end in occupied):
                continue
            occupied.append(span)
            matches.append((phrase, visual))
            break
    return matches


def _category(text: str) -> str:
    normalized = _strip_accents(text.lower())
    tokens = set(_tokens(normalized))
    best_category = "general"
    best_score = 0
    for category, terms in _CATEGORY_HINTS.items():
        score = 0
        for term in terms:
            norm_term = _strip_accents(term)
            if " " in norm_term:
                if norm_term in normalized:
                    score += 3
            else:
                if norm_term in tokens:
                    score += 1
        if score > best_score:
            best_category, best_score = category, score
    return best_category


def _mood(text: str) -> str:
    normalized = set(_tokens(_strip_accents(text.lower())))
    positive = len(normalized & {_strip_accents(x) for x in _MOOD_TERMS["positive"]})
    negative = len(normalized & {_strip_accents(x) for x in _MOOD_TERMS["negative"]})
    if positive > negative:
        return "optimistic"
    if negative > positive:
        return "serious"
    return "neutral"


class VisualQueryEngine:
    def __init__(self, document_text: str) -> None:
        self.document_text = document_text
        self.language = _detect_language(document_text)
        self.global_keywords = self._extract_global_keywords(document_text)
        self.global_category = _category(document_text)
        self.theme_anchor = _THEME_ANCHORS.get(self.global_category, _THEME_ANCHORS["general"])

    def _extract_global_keywords(self, text: str) -> list[str]:
        stopwords = _VI_STOPWORDS | _EN_STOPWORDS
        tokens = [token for token in _tokens(text) if token not in stopwords and len(token) > 2 and not token.isdigit()]
        counts = Counter(tokens)
        return [token for token, _ in counts.most_common(8)]

    def _local_keywords(self, text: str) -> list[str]:
        stopwords = _VI_STOPWORDS | _EN_STOPWORDS
        tokens = [token for token in _tokens(text) if token not in stopwords and len(token) > 2 and not token.isdigit()]
        counts = Counter(tokens)
        first_position = {token: tokens.index(token) for token in set(tokens)}
        ranked = sorted(counts, key=lambda token: (-counts[token], first_position[token], -len(token)))
        return ranked[:8]

    def build_plan(self, segment: Segment) -> QueryPlan:
        text = segment.text
        phrase_visuals = [visual for _, visual in _phrase_matches(text)]
        local_keywords = self._local_keywords(text)
        local_cat = _category(text)

        # STRICT THEME LOCK: Force category to global_category unless segment has strong explicit domain terms
        if local_cat != self.global_category and self.global_category != "general":
            category = self.global_category
        else:
            category = local_cat if local_cat != "general" else self.global_category

        mood = _mood(text)

        mapped_single: list[str] = []
        for keyword in local_keywords:
            mapped = _SINGLE_MAP.get(keyword) or _VI_KEYWORD_TRANSLATIONS.get(keyword)
            if mapped:
                mapped_single.append(mapped)

        visual_terms: list[str] = []
        for term in [*phrase_visuals, *mapped_single]:
            if term not in visual_terms:
                visual_terms.append(term)

        # MANDATORY THEME ANCHOR: Ensure query ALWAYS contains global theme anchor!
        if visual_terms:
            primary = " ".join(visual_terms[:2])
            if self.theme_anchor and self.theme_anchor not in primary:
                primary = f"{self.theme_anchor} {primary}"
        else:
            primary = _FALLBACKS.get(category, _FALLBACKS["general"])

        if mood == "optimistic" and "success" not in primary and category in {"business", "fitness", "food"}:
            primary += " happy"
        elif mood == "serious" and category in {"business", "technology", "history", "healthcare"}:
            primary += " serious"

        fallback = _FALLBACKS.get(category, _FALLBACKS["general"])
        raw_keyword_query = " ".join(local_keywords[:5])
        translated_keywords = " ".join([_VI_KEYWORD_TRANSLATIONS.get(k, k) for k in local_keywords[:4] if k not in _VI_STOPWORDS])
        alternates: list[str] = []

        if fallback.lower() != primary.lower():
            alternates.append(fallback)
        if self.language == "en" and raw_keyword_query:
            alternates.append(f"{self.theme_anchor} {raw_keyword_query}")
        elif self.language == "vi":
            if translated_keywords and translated_keywords != raw_keyword_query:
                alternates.append(f"{self.theme_anchor} {translated_keywords}")
            if raw_keyword_query:
                alternates.append(f"{self.theme_anchor} {raw_keyword_query}")

        keywords = local_keywords[:6]
        visual_intent = f"{category}:{mood}"
        return QueryPlan(
            primary_query=_compress_query(primary),
            alternate_queries=[(_compress_query(q) if not _VI_SIGNAL_QUERY.search(q) else " ".join(q.split())[:120]) for q in alternates[:3]],
            locale="vi-VN" if self.language == "vi" else "en-US",
            visual_intent=visual_intent,
            keywords=keywords,
        )
