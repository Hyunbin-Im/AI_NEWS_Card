# -*- coding: utf-8 -*-
"""
대시보드 생성기 — articles.json → index.html
=============================================
사용법:
    python generator.py                    # articles.json 사용
    python generator.py sample_articles.json   # 샘플 데이터로 데모 생성

핵심 설계 포인트 (원본 사이트의 실패에서 배운 것):
1. 경쟁사 매칭에 한글 경계 검사 → '미토스' 안의 '토스' 오탐 방지
2. 점수 산출 근거를 기사마다 기록 → "왜 37점인가"에 답할 수 있음
3. 인사이트는 '자동 태깅'으로 정직하게 표기 (룰 기반임을 숨기지 않음)
"""
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta

from config import (SITE, KEYWORD_WEIGHTS, COMPETITORS, INSIGHT_RULES, TABS)

KST = timezone(timedelta(hours=9))


# ── 1. 매칭 (오탐 방지가 핵심) ────────────────────────────────
def match_korean_word(term: str, text: str) -> bool:
    """한글 경계 매칭: term 앞뒤에 다른 한글이 붙어 있으면 매칭하지 않는다.
    예: '미토스'에서 '토스'는 앞이 한글('미')이므로 불일치.
        '토스뱅크'는 뒤가 한글이므로 '토스' 단독 언급으로 보지 않는다
        → 필요하면 COMPETITORS에 '토스뱅크'를 별도 등록.
    """
    pattern = r"(?<![가-힣])" + re.escape(term) + r"(?![가-힣])"
    return re.search(pattern, text) is not None


def analyze(article: dict) -> dict:
    """기사 하나를 점수화하고 근거를 남긴다."""
    text = article["title"] + " " + article.get("summary", "")
    score, matched_groups, matched_terms, reasons = 0, [], [], []

    for group, spec in KEYWORD_WEIGHTS.items():
        hits = [t for t in spec["terms"] if match_korean_word(t, text)]
        if hits:
            gained = spec["weight"] + (len(hits) - 1) * 2  # 다중 히트 보너스
            score += gained
            matched_groups.append(group)
            matched_terms.extend(hits)
            reasons.append(f"{group}({', '.join(hits)}) +{gained}")

    competitors = [c for c in COMPETITORS if match_korean_word(c, text)]
    if competitors:
        score += 6
        reasons.append(f"경쟁사({', '.join(competitors)}) +6")

    # 최신성 보너스: 3시간 이내 +3
    age_h = (datetime.now(KST) - datetime.fromisoformat(article["published"])).total_seconds() / 3600
    if age_h <= 3:
        score += 3
        reasons.append("최신(3h 이내) +3")

    article.update({
        "score": score,
        "groups": matched_groups,
        "terms": matched_terms,
        "competitors": competitors,
        "score_reasons": reasons,   # ← 점수 근거를 투명하게 저장
    })
    return article


# ── 2. 유사 중복 클러스터링 ──────────────────────────────────
def tokenize(title: str) -> set:
    return set(re.findall(r"[가-힣A-Za-z0-9]{2,}", title))


def cluster(articles: list[dict]) -> list[dict]:
    """제목 토큰 자카드 유사도 0.5 이상이면 동일 사건으로 묶는다."""
    out = []
    for a in articles:
        ta = tokenize(a["title"])
        for rep in out:
            tb = tokenize(rep["title"])
            j = len(ta & tb) / max(1, len(ta | tb))
            if j >= 0.5:
                rep.setdefault("duplicates", []).append(
                    {"title": a["title"], "url": a["url"], "source": a.get("source", "")})
                break
        else:
            out.append(a)
    return out


# ── 3. 인사이트 (룰 기반 v1 — LLM 교체 지점) ──────────────────
def make_insights(article: dict) -> list[str]:
    insights = []
    for rule in INSIGHT_RULES:
        if rule.get("when_competitor") and article["competitors"]:
            insights.append(rule["text"].format(names=", ".join(article["competitors"])))
        elif rule.get("when_group") in article["groups"]:
            terms = [t for t in article["terms"]
                     if t in KEYWORD_WEIGHTS[rule["when_group"]]["terms"]]
            insights.append(rule["text"].format(terms=", ".join(terms)))
        if len(insights) >= 3:
            break
    return insights

    # ── v2 업그레이드 과제 ──
    # 위 룰 대신 Claude API 호출로 교체하면 기사 맥락을 실제로 읽는 인사이트가 된다:
    #   client.messages.create(model="claude-haiku-...", max_tokens=200,
    #       messages=[{"role": "user", "content":
    #           f"하나카드 전략기획 관점에서 이 기사의 시사점 2줄: {title} {summary}"}])
    # 비용: 기사당 약 1~2원. 상위 20건만 호출하면 하루 40원 수준.


# ── 4. HTML 생성 ─────────────────────────────────────────────
def classify_tab(article: dict) -> str:
    text = article["title"] + " " + article.get("summary", "")
    for tab_name, terms in TABS:
        if any(match_korean_word(t, text) or t in text for t in terms):
            return tab_name
    return "기타"


def esc(s):
    return html.escape(str(s), quote=True)


def render(data: dict) -> str:
    meta = data["meta"]
    articles = [analyze(a) for a in data["articles"]]
    articles = [a for a in articles if a["score"] >= 8]  # 관련성 컷 (precision 우선)
    articles.sort(key=lambda a: -a["score"])
    articles = cluster(articles)
    top = articles[:SITE["top_n"]]

    hour_dist = Counter(datetime.fromisoformat(a["published"]).strftime("%H시") for a in articles)
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    c = SITE["theme_color"]

    tabs = {}
    for a in top:
        tabs.setdefault(classify_tab(a), []).append(a)

    cards = []
    medals = ["🥇", "🥈", "🥉"]
    for i, a in enumerate(top):
        rank = medals[i] if i < 3 else str(i + 1)
        t = datetime.fromisoformat(a["published"]).strftime("%m-%d %H:%M")
        chips = "".join(f'<span class="chip">{esc(k)}</span>' for k in dict.fromkeys(a["terms"][:6]))
        comp = "".join(f'<span class="chip comp">{esc(k)}</span>' for k in a["competitors"])
        insights = "".join(f"<li>{esc(s)}</li>" for s in make_insights(a))
        dups = ""
        if a.get("duplicates"):
            links = " · ".join(f'<a href="{esc(d["url"])}">{esc(d["source"] or "링크")}</a>'
                               for d in a["duplicates"][:3])
            dups = f'<div class="dups">📎 동일 사건 보도 {len(a["duplicates"])}건 · {links}</div>'
        reasons = esc(" / ".join(a["score_reasons"]))
        cards.append(f"""
    <article class="card" data-tab="{esc(classify_tab(a))}">
      <div class="rank">{rank}</div>
      <div class="body">
        <a class="title" href="{esc(a['url'])}" target="_blank">{esc(a['title'])}</a>
        <div class="meta">🕒 {t} · {esc(a.get('source',''))} ·
          <span class="score" title="{reasons}">점수 {a['score']} ⓘ</span></div>
        <div class="chips">{chips}{comp}</div>
        <div class="insight"><b>🏷️ 자동 태깅</b><ul>{insights or '<li>일반 동향 — 참고용</li>'}</ul></div>
        {dups}
      </div>
    </article>""")

    tab_buttons = '<button class="tab on" data-tab="전체">📋 전체 ({})</button>'.format(len(top))
    tab_buttons += "".join(
        f'<button class="tab" data-tab="{esc(name)}">{esc(name)} ({len(items)})</button>'
        for name, items in tabs.items())

    bars = ""
    if hour_dist:
        mx = max(hour_dist.values())
        for h in sorted(hour_dist):
            pct = int(hour_dist[h] / mx * 100)
            bars += (f'<div class="bar-wrap"><div class="bar" style="height:{pct}%"></div>'
                     f'<span>{h}<br>{hour_dist[h]}</span></div>')

    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="{c}">
<title>{esc(SITE['title'])} — {now}</title>
<style>
  :root {{ --c: {c}; }}
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ font-family: 'Apple SD Gothic Neo','Malgun Gothic',sans-serif; background:#f4f7f7; color:#1e2b2b; }}
  header {{ background: var(--c); color:#fff; padding:16px 20px; }}
  header .sub {{ opacity:.85; font-size:12px; letter-spacing:1px; }}
  header h1 {{ font-size:20px; margin-top:4px; }}
  .stats {{ display:flex; gap:10px; padding:14px 20px; flex-wrap:wrap; }}
  .stat {{ background:#fff; border-radius:10px; padding:10px 18px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .stat b {{ font-size:20px; color:var(--c); display:block; }}
  .stat span {{ font-size:12px; color:#667; }}
  .dist {{ background:#fff; margin:0 20px 14px; border-radius:10px; padding:12px 16px 4px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .dist h3 {{ font-size:13px; color:#455; margin-bottom:8px; }}
  .bars {{ display:flex; gap:6px; align-items:flex-end; height:80px; }}
  .bar-wrap {{ flex:1; display:flex; flex-direction:column; justify-content:flex-end; align-items:center; height:100%; }}
  .bar {{ width:70%; background:var(--c); border-radius:3px 3px 0 0; min-height:3px; }}
  .bar-wrap span {{ font-size:10px; color:#667; text-align:center; margin-top:3px; }}
  .tabs {{ padding:0 20px 10px; display:flex; gap:8px; flex-wrap:wrap; }}
  .tab {{ border:1px solid #cdd; background:#fff; border-radius:20px; padding:6px 14px; cursor:pointer; font-size:13px; }}
  .tab.on {{ background:var(--c); color:#fff; border-color:var(--c); }}
  main {{ padding:0 20px 40px; max-width:860px; }}
  .card {{ background:#fff; border-radius:10px; padding:14px 16px; margin-bottom:12px; display:flex; gap:12px; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
  .rank {{ font-size:18px; font-weight:700; color:var(--c); min-width:32px; }}
  .title {{ font-weight:700; color:#123; text-decoration:none; font-size:15px; }}
  .title:hover {{ color:var(--c); }}
  .meta {{ font-size:12px; color:#667; margin:4px 0; }}
  .score {{ cursor:help; border-bottom:1px dotted #999; }}
  .chips {{ margin:4px 0; }}
  .chip {{ display:inline-block; background:#e4f1f0; color:#0a6b66; border-radius:12px; padding:2px 9px; font-size:11px; margin:2px 3px 2px 0; }}
  .chip.comp {{ background:#fdeaea; color:#b03030; }}
  .insight {{ background:#f7fbfa; border-left:3px solid var(--c); padding:8px 12px; border-radius:0 8px 8px 0; margin-top:6px; font-size:13px; }}
  .insight ul {{ margin:4px 0 0 18px; }}
  .dups {{ font-size:12px; color:#778; margin-top:6px; }}
  footer {{ text-align:center; color:#899; font-size:12px; padding:20px; }}
</style></head>
<body>
<header>
  <div class="sub">{esc(SITE['subtitle'])}</div>
  <h1>💳 {esc(SITE['title'])} — 카드·페이먼트 AI 주요뉴스</h1>
</header>
<div class="stats">
  <div class="stat"><b>{meta.get('collected','–')}</b><span>수집 건수</span></div>
  <div class="stat"><b>{meta.get('in_window','–')}</b><span>시간창 내</span></div>
  <div class="stat"><b>{len(articles)}</b><span>관련 판정 (컷 8점)</span></div>
  <div class="stat"><b>{now}</b><span>기준 시각 (KST)</span></div>
</div>
<div class="dist"><h3>🕒 시간대별 관련 기사 분포</h3><div class="bars">{bars}</div></div>
<div class="tabs">{tab_buttons}</div>
<main>{''.join(cards)}</main>
<footer>인사이트는 룰 기반 자동 태깅입니다 (v1) · 점수에 마우스를 올리면 산출 근거가 보입니다 · 내부 프로토타입</footer>
<script>
document.querySelectorAll('.tab').forEach(b => b.onclick = () => {{
  document.querySelectorAll('.tab').forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  const t = b.dataset.tab;
  document.querySelectorAll('.card').forEach(cd =>
    cd.style.display = (t === '전체' || cd.dataset.tab === t) ? 'flex' : 'none');
}});
</script>
</body></html>"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "articles.json"
    with open(src, encoding="utf-8") as f:
        data = json.load(f)
    html_out = render(data)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"index.html 생성 완료 (입력: {src}, 기사 {len(data['articles'])}건)")


if __name__ == "__main__":
    main()
