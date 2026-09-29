from datetime import datetime, timedelta, timezone
from io import BytesIO

from server.trend_sources import GoogleTrendsBrazilRSS, TrendEvidence, rank_public_signal


class Response(BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


def test_google_rss_normalizes_public_brazil_signal_and_keeps_missing_unknown():
    xml = b'''<?xml version="1.0"?><rss xmlns:ht="https://trends.google.com/trending/rss"><channel><item>
      <title>tema em alta</title><pubDate>Mon, 28 Sep 2026 20:00:00 +0000</pubDate>
      <ht:approx_traffic>2,000+</ht:approx_traffic><ht:news_item><ht:news_item_title>Refer\xc3\xaancia</ht:news_item_title></ht:news_item>
    </item></channel></rss>'''
    provider = GoogleTrendsBrazilRSS(opener=lambda *_args, **_kwargs: Response(xml))
    [item] = provider.collect()
    assert item.market == "BR" and item.geography == "BR_SIGNAL"
    assert item.language == "UNKNOWN"
    assert item.metrics["google_approx_traffic_raw"] == "2,000+"
    assert item.metrics["views"] is None and item.metrics["likes"] is None
    assert item.metrics["video_reference_id"] is None
    assert item.source == "GOOGLE_TRENDS_RSS"


def test_ranking_is_reproducible_and_does_not_impute_tiktok_engagement():
    observed = datetime(2026, 9, 28, 10, tzinfo=timezone.utc)
    item = TrendEvidence("t", "tema", "GOOGLE_TRENDS_RSS", "https://example.test/rss", "BR", "BR_SIGNAL", "UNKNOWN",
                         observed, observed, {"google_approx_traffic_raw": "20,000+", "views": None}, "evidence")
    now = observed + timedelta(hours=2)
    first = rank_public_signal(item, now)
    assert first == rank_public_signal(item, now)
    assert first["score"] == 42.67
    assert first["components"]["engagement_rate"] is None
    assert first["components"]["tiktok_velocity"] is None
    unknown = TrendEvidence("t2", "tema2", "RSS", "https://example.test", "BR", "BR_SIGNAL", "UNKNOWN",
                            observed, observed, {"google_approx_traffic_raw": None}, "evidence")
    assert rank_public_signal(unknown, now)["components"]["google_search_interest_0_30"] is None
