# -*- coding: utf-8 -*-
"""
뉴스 수집기 — Google News RSS 기반 (API 키 불필요)
====================================================
사용법:
    python collector.py            # articles.json 생성
    python collector.py && python generator.py   # 수집 후 대시보드 생성

네이버 뉴스 검색 API를 쓰려면 fetch_naver()에 클라이언트 키를 넣고
main()에서 호출을 교체하세요 (하루 25,000건 무료, 국내 기사 커버리지가 더 좋음).
"""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

from config import SEARCH_QUERIES, SITE

KST = timezone(timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (hanacard-newsbot; internal prototype)"}


def fetch_google_news(query: str) -> list[dict]:
    """Google News RSS에서 검색어별 기사 목록을 가져온다."""
    url = (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=ko&gl=KR&ceid=KR:ko"
    )
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        root = ET.fromstring(r.read())

    articles = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate") or ""
        source = item.findtext("source") or ""
        try:
            published = parsedate_to_datetime(pub).astimezone(KST)
        except Exception:
            continue  # 날짜 파싱 실패 기사는 버린다 (원본 사이트의 인코딩 깨짐 노출 교훈)
        if not title or not link:
            continue
        articles.append({
            "title": title,
            "url": link,
            "source": source,
            "published": published.isoformat(),
            "matched_query": query,
        })
    return articles


def within_window(articles: list[dict], hours: int) -> list[dict]:
    cutoff = datetime.now(KST) - timedelta(hours=hours)
    return [a for a in articles if datetime.fromisoformat(a["published"]) >= cutoff]


def dedupe_exact(articles: list[dict]) -> list[dict]:
    """URL/제목 완전 중복 제거 (유사 중복 클러스터링은 generator에서)."""
    seen, out = set(), []
    for a in articles:
        key = re.sub(r"\s+", "", a["title"])
        if key in seen or a["url"] in seen:
            continue
        seen.add(key)
        seen.add(a["url"])
        out.append(a)
    return out


def main():
    all_articles = []
    for q in SEARCH_QUERIES:
        try:
            batch = fetch_google_news(q)
            print(f"  [{q}] {len(batch)}건")
            all_articles.extend(batch)
        except Exception as e:
            print(f"  [{q}] 실패: {e}")  # 한 쿼리 실패가 전체를 죽이지 않게

    collected = len(all_articles)
    all_articles = dedupe_exact(all_articles)
    all_articles = within_window(all_articles, SITE["window_hours"])
    all_articles.sort(key=lambda a: a["published"], reverse=True)

    meta = {
        "collected": collected,
        "in_window": len(all_articles),
        "generated_at": datetime.now(KST).isoformat(),
    }
    with open("articles.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "articles": all_articles}, f,
                  ensure_ascii=False, indent=1)
    print(f"수집 {collected}건 → 시간창 내 {len(all_articles)}건 → articles.json 저장")


if __name__ == "__main__":
    main()
