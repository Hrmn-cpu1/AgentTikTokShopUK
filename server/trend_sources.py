"""Public, unauthenticated trend sources. TikTok-only metrics stay UNKNOWN."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from typing import Protocol

TRENDS_RSS = "https://trends.google.com/trending/rss?geo=BR"
HT = "https://trends.google.com/trending/rss"


@dataclass(frozen=True)
class TrendEvidence:
    trend_id: str
    topic: str
    source: str
    source_ref: str
    market: str
    geography: str
    language: str
    collected_at: datetime
    observed_at: datetime
    metrics: dict
    evidence: str


class TrendSource(Protocol):
    def collect(self) -> list[TrendEvidence]: ...


class GoogleTrendsBrazilRSS:
    """Google public Trending Now RSS filtered to Brazil; not TikTok trend data."""

    source = "GOOGLE_TRENDS_RSS"

    def __init__(self, timeout: float = 12, opener=None):
        self.timeout = timeout
        self.opener = opener or urllib.request.urlopen

    def collect(self) -> list[TrendEvidence]:
        request = urllib.request.Request(TRENDS_RSS, headers={"User-Agent": "AgentTikTokShop/1.0 (public trend RSS)"})
        with self.opener(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise RuntimeError(f"Google Trends RSS returned HTTP {response.status}")
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise RuntimeError("Google Trends RSS exceeds the 1 MB safety limit")
        root = ET.fromstring(raw)
        now = datetime.now(timezone.utc)
        out = []
        for item in root.findall("./channel/item"):
            topic = (item.findtext("title") or "").strip()
            date_text = (item.findtext("pubDate") or "").strip()
            if not topic or not date_text:
                continue
            observed = parsedate_to_datetime(date_text)
            if observed.tzinfo is None:
                continue
            observed = observed.astimezone(timezone.utc)
            traffic = (item.findtext(f"{{{HT}}}approx_traffic") or "").strip() or None
            news = []
            for node in item.findall(f"{{{HT}}}news_item"):
                news.append({
                    "title": (node.findtext(f"{{{HT}}}news_item_title") or "").strip() or None,
                    "url": (node.findtext(f"{{{HT}}}news_item_url") or "").strip() or None,
                    "source": (node.findtext(f"{{{HT}}}news_item_source") or "").strip() or None,
                })
            digest = hashlib.sha256((self.source + "|BR|" + topic.casefold()).encode()).hexdigest()[:24]
            out.append(TrendEvidence(
                trend_id="gtr-br-" + digest, topic=topic, source=self.source,
                source_ref=TRENDS_RSS, market="BR", geography="BR_SIGNAL", language="UNKNOWN",
                collected_at=now, observed_at=observed,
                metrics={"google_approx_traffic_raw": traffic, "views": None, "likes": None,
                         "comments": None, "shares": None, "tiktok_velocity": None,
                         "hashtags": None, "sound_reference": None, "video_reference_id": None,
                         "news_references": news},
                evidence=f"Google Trends Trending Now RSS item: {topic}; reported traffic={traffic or 'UNKNOWN'}; TikTok metrics=UNKNOWN.",
            ))
        return out


def rank_public_signal(item: TrendEvidence, now: datetime | None = None) -> dict:
    """Reproducible search-signal score, deliberately distinct from TikTok engagement."""
    now = now or datetime.now(timezone.utc)
    age_hours = max(0.0, (now.astimezone(timezone.utc) - item.observed_at).total_seconds() / 3600)
    recency = round(max(0.0, 40.0 * (1 - min(age_hours, 24) / 24)), 2)
    raw = item.metrics.get("google_approx_traffic_raw")
    numeric = None
    if isinstance(raw, str):
        digits = "".join(ch for ch in raw if ch.isdigit())
        numeric = int(digits) if digits else None
    search_interest = round(30 * min(numeric / 100_000, 1), 2) if numeric is not None else None
    # Unknown components are omitted and never imputed.
    known = [recency] + ([search_interest] if search_interest is not None else [])
    score = round(sum(known), 2)
    return {"score": score, "components": {"recency_0_40": recency,
        "google_search_interest_0_30": search_interest, "tiktok_velocity": None,
        "engagement_rate": None, "share_signal": None, "comment_signal": None,
        "geography": "BR_SIGNAL", "age_hours": round(age_hours, 2),
        "source_kind": "PUBLIC_SEARCH_SIGNAL"}}
