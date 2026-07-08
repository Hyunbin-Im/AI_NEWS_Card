# 💳 하나카드 뉴스봇 (프로토타입)

카드·페이먼트 도메인 관점의 뉴스 자동 수집·랭킹·브리핑 대시보드.
[finance-ai-newsbot](https://finance-ai-newsbot.vercel.app/)의 구조를 참고하되,
원본의 문제점(경쟁사 오탐, 점수 근거 불투명, 룰 인사이트의 과대 포장)을 고쳐서 설계했다.

## 구조

```
config.py            ← 도메인 지식 전부 (키워드, 경쟁사, 인사이트 룰, 탭)
collector.py         ← Google News RSS 수집 → articles.json
generator.py         ← 점수화·클러스터링·태깅 → index.html
sample_articles.json ← 데모용 실제 기사 데이터 (2026-07-08)
index.html           ← 생성된 대시보드 (샘플 데이터 기준)
.github/workflows/   ← 30분 주기 자동 갱신 (GitHub Actions)
```

**핵심 설계 원칙**: 코드(collector/generator)와 도메인 지식(config)의 분리.
config.py만 바꾸면 은행/증권/보험용으로 재사용된다.

## 실행

```bash
python collector.py                      # 뉴스 수집 (인터넷 필요)
python generator.py                      # articles.json → index.html
python generator.py sample_articles.json # 샘플 데이터로 데모 확인
```

의존성 없음 — 파이썬 표준 라이브러리만 사용.

## 배포 (무료 조합)

1. GitHub에 리포 생성 (private 권장) 후 이 폴더를 push
2. [Vercel](https://vercel.com)에서 리포 연결 → 정적 사이트로 자동 배포
3. `.github/workflows/update.yml`이 30분마다 수집·커밋 → Vercel 자동 재배포
4. **사내 정보 도구라면 반드시 Vercel의 Password Protection 또는 사내망 배포를 적용할 것**
   (원본 사이트는 그룹 브랜딩을 단 채 인증 없이 공개되어 있었다 — 반면교사)

## 원본과 달라진 점

| 항목 | 원본 (finance-ai-newsbot) | 이 프로토타입 |
|---|---|---|
| 경쟁사 매칭 | 부분 문자열 → "미토스"에서 "토스" 오탐 | 한글 경계 정규식 매칭 |
| 점수 | 근거 미공개 | 기사마다 산출 근거 저장, UI 툴팁 노출 |
| 인사이트 | "💡 인사이트"로 포장된 룰 템플릿 | "🏷️ 자동 태깅"으로 정직하게 표기 |
| 관련성 판정 | recall 위주 (1,085건 "관련") | 컷 점수 8점, precision 우선 |
| 도메인 | 코드에 하드코딩 | config.py로 분리 (멀티 테넌트) |

## 후배들에게 주는 업그레이드 과제

1. **(쉬움)** config.py 키워드 튜닝 — 일주일 돌려보고 노이즈/누락 기사로 가중치 보정
2. **(쉬움)** 네이버 뉴스 검색 API 연동 — 국내 기사 커버리지 개선 (collector.py 주석 참고)
3. **(중간)** 브리핑 아카이브 — 하루 1~2회 스냅샷을 `briefings/YYYY-MM-DD.html`로 저장
4. **(중간)** 요약 품질 — RSS에는 본문이 없으므로 기사 본문 크롤링 + 3줄 요약 추가
5. **(핵심)** 인사이트 v2 — generator.py의 `make_insights()`를 Claude API 호출로 교체.
   상위 20건만 호출하면 하루 40~50원 수준. 이것 하나로 원본과 급이 달라진다.
6. **(심화)** 임베딩 기반 관련성 판정 — 키워드 매칭의 한계(동의어, 문맥)를 넘기

## 주의

- 기사 본문을 저장·재배포하지 말 것 (저작권). 제목+링크+짧은 발췌까지만.
- 사명·로고 사용은 사내 브랜드 가이드라인 확인 후 적용할 것.
