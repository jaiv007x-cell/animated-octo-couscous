from app.evidence import evidence_tier
from app.models import SourceType, EvidenceTier


def test_official_gov_is_definitive():
    tier, score, review = evidence_tier(SourceType.official, "https://excise.delhi.gov.in/notifications", "Dry day order", "")
    assert tier == EvidenceTier.official_confirmed
    assert score > 0.8
    assert review is False


def test_news_is_not_definitive():
    tier, score, review = evidence_tier(SourceType.news, "https://timesofindia.indiatimes.com/example", "Excise fee hike", "")
    assert tier == EvidenceTier.reported_not_confirmed
    assert review is True


def test_social_is_chatter():
    tier, score, review = evidence_tier(SourceType.social, "manual://whatsapp", "Rumour", "")
    assert tier == EvidenceTier.chatter_unverified
    assert review is True
