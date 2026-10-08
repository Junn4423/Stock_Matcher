from app.models import Segment
from app.services.query_engine import VisualQueryEngine


def test_vietnamese_tech_query_becomes_visual_english() -> None:
    text = "Trí tuệ nhân tạo giúp lập trình viên phân tích dữ liệu và bảo mật hệ thống."
    engine = VisualQueryEngine(text)
    plan = engine.build_plan(Segment(1, text, 1, 12, 5.5))
    assert "artificial intelligence" in plan.primary_query.lower()
    assert plan.visual_intent.startswith("technology")
    assert plan.all_queries


def test_healthcare_query_detects_clinic_scene() -> None:
    text = "Bác sĩ xem hồ sơ bệnh án và trao đổi với bệnh nhân."
    plan = VisualQueryEngine(text).build_plan(Segment(1, text, 1, 11, 5.0))
    joined = " ".join(plan.all_queries).lower()
    assert "doctor" in joined or "clinic" in joined
