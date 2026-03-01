#!/usr/bin/env python3
"""파주시장 선거 뉴스 수집, 분석 및 대시보드 데이터 갱신 스크립트"""

import os
import sys
import json
import argparse
import time
import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from collections import Counter
from urllib.parse import quote

import requests

NAVER_API_URL = "https://openapi.naver.com/v1/search/news.json"

PRIMARY_KEYWORDS = [
    "파주시장 선거", "파주시장 후보", "2026 파주시장"
]
CANDIDATE_KEYWORDS = [
    "조성환 파주", "김경일 파주", "고준호 파주", "안명규 파주",
    "손배찬 파주", "이용욱 파주", "조일출 파주", "이재희 파주"
]
ISSUE_KEYWORDS = [
    "파주 GTX", "파주 메디컬클러스터", "파주 종합병원",
    "파주 운정", "파주 군사시설", "파주페이"
]
ALL_KEYWORDS = PRIMARY_KEYWORDS + CANDIDATE_KEYWORDS + ISSUE_KEYWORDS

CANDIDATE_NAMES = [
    "조성환", "김경일", "고준호", "안명규",
    "손배찬", "이용욱", "조일출", "이재희", "최유각"
]

ELECTION_DATE = datetime(2026, 6, 3)

# 감성분석용 키워드 사전
POSITIVE_WORDS = [
    "성과", "확대", "지원", "개선", "혁신", "추진", "발전", "강화", "협력", "합의",
    "기대", "호평", "성공", "약속", "비전", "공약", "계획", "도약", "상승", "선두",
    "지지", "환영", "긍정", "돌파", "활성화", "투자", "유치", "개통", "착공", "완공"
]
NEGATIVE_WORDS = [
    "논란", "비판", "실패", "갈등", "반발", "의혹", "문제", "위기", "우려", "지적",
    "반대", "거부", "파문", "사퇴", "고발", "기소", "수사", "부정", "비리", "하락",
    "폭로", "규탄", "항의", "불만", "좌절", "지연", "무산", "철회", "중단", "파행"
]

# 이슈 카테고리 매핑
ISSUE_CATEGORIES = {
    "교통/GTX": ["GTX", "교통", "PBRT", "DRT", "철도", "버스", "3호선"],
    "의료/병원": ["종합병원", "메디컬", "의료", "병원", "달빛", "의과대학"],
    "균형발전": ["운정", "원도심", "구도심", "문산", "균형", "양극화"],
    "군사규제": ["군사시설", "보호구역", "캠프", "접경", "규제"],
    "경제/일자리": ["경제자유구역", "블록체인", "테크노밸리", "일자리", "기업", "창업"],
    "교육 인프라": ["교육", "학교", "과밀", "과소", "학부모", "AI학습"],
    "안전/인프라": ["상수도", "단수", "안전", "CPTED", "소방", "재난"],
    "문화/관광": ["DMZ", "비엔날레", "관광", "문화", "영어마을", "미디어아트"]
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
DATA_DIR = os.path.join(PROJECT_DIR, "data")


def strip_html(text):
    """HTML 태그 및 엔티티 제거"""
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&apos;", "'")
    return text.strip()


def search_naver_news(client_id, client_secret, query, display=100, start=1):
    """네이버 뉴스 검색 API 호출"""
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": query,
        "display": display,
        "start": start,
        "sort": "date",
    }
    resp = requests.get(NAVER_API_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()


def parse_pub_date(pub_date_str):
    """네이버 API pubDate (RFC 2822) 파싱"""
    try:
        return parsedate_to_datetime(pub_date_str)
    except Exception:
        return None


def collect_articles(client_id, client_secret, keywords, period_start, period_end):
    """키워드별 기사 수집 및 기간 필터링"""
    seen = set()
    articles = []

    for keyword in keywords:
        try:
            data = search_naver_news(client_id, client_secret, keyword)
        except Exception as e:
            print(f"[경고] '{keyword}' 검색 실패: {e}", file=sys.stderr)
            time.sleep(0.1)
            continue

        for item in data.get("items", []):
            link = item.get("originallink") or item.get("link", "")
            if link in seen:
                continue
            seen.add(link)

            pub_dt = parse_pub_date(item.get("pubDate", ""))
            if pub_dt is None:
                continue
            if pub_dt < period_start or pub_dt > period_end:
                continue

            title_clean = strip_html(item.get("title", ""))
            desc_clean = strip_html(item.get("description", ""))
            text = title_clean + " " + desc_clean

            mentioned = [name for name in CANDIDATE_NAMES if name in text]

            articles.append({
                "title": title_clean,
                "link": item.get("link", ""),
                "originallink": link,
                "description": desc_clean[:200],
                "pubDate": pub_dt.isoformat(),
                "candidates_mentioned": mentioned,
                "keywords_matched": [keyword],
            })

        time.sleep(0.1)

    articles.sort(key=lambda a: a["pubDate"], reverse=True)
    return articles


def analyze_sentiment(text):
    """키워드 기반 감성분석"""
    pos_count = sum(1 for w in POSITIVE_WORDS if w in text)
    neg_count = sum(1 for w in NEGATIVE_WORDS if w in text)
    total = pos_count + neg_count
    if total == 0:
        return {"positive": 0, "negative": 0, "neutral": 1}
    return {
        "positive": pos_count / total,
        "negative": neg_count / total,
        "neutral": 0
    }


def analyze_articles(articles):
    """기사 분석: 후보 언급, 키워드, 감성, 이슈, 일별 기사 수"""
    candidate_counter = Counter()
    keyword_counter = Counter()
    daily_counter = Counter()
    candidate_sentiment = {name: {"pos": 0, "neg": 0, "total": 0} for name in CANDIDATE_NAMES}
    issue_counter = {cat: 0 for cat in ISSUE_CATEGORIES}

    for article in articles:
        text = article["title"] + " " + article["description"]

        for name in article["candidates_mentioned"]:
            candidate_counter[name] += 1
            sent = analyze_sentiment(text)
            candidate_sentiment[name]["pos"] += sent["positive"]
            candidate_sentiment[name]["neg"] += sent["negative"]
            candidate_sentiment[name]["total"] += 1

        for kw in ["GTX", "종합병원", "메디컬", "운정", "교통", "경제자유구역",
                    "군사시설", "DMZ", "블록체인", "AI", "파주페이", "교육",
                    "민주당", "국민의힘", "경선", "여론조사"]:
            if kw in text:
                keyword_counter[kw] += 1

        for category, keywords in ISSUE_CATEGORIES.items():
            if any(kw in text for kw in keywords):
                issue_counter[category] += 1

        day = article["pubDate"][:10]
        daily_counter[day] += 1

    candidate_mentions = [
        {"name": name, "count": candidate_counter.get(name, 0)}
        for name in CANDIDATE_NAMES
        if candidate_counter.get(name, 0) > 0
    ]
    candidate_mentions.sort(key=lambda x: x["count"], reverse=True)

    top_keywords = [
        {"keyword": kw, "count": cnt}
        for kw, cnt in keyword_counter.most_common(10)
    ]

    article_count_by_day = dict(sorted(daily_counter.items()))

    return {
        "candidate_mentions": candidate_mentions,
        "top_keywords": top_keywords,
        "article_count_by_day": article_count_by_day,
        "candidate_sentiment": candidate_sentiment,
        "issue_counter": issue_counter,
    }


def build_report(report_type, date_str, period_start, period_end, articles, analysis):
    """보고서 JSON 구성"""
    return {
        "meta": {
            "type": report_type,
            "date": date_str,
            "period_start": period_start.strftime("%Y-%m-%d"),
            "period_end": period_end.strftime("%Y-%m-%d"),
            "generated_at": datetime.now().isoformat(),
            "total_articles_found": len(articles),
            "keywords_used": ALL_KEYWORDS,
        },
        "summary": {
            "candidate_mentions": analysis["candidate_mentions"],
            "top_keywords": analysis["top_keywords"],
            "article_count_by_day": analysis["article_count_by_day"],
        },
        "articles": articles,
    }


def update_manifest(report_type, date_str, filename, article_count):
    """reports/index.json 매니페스트 업데이트"""
    manifest_path = os.path.join(REPORTS_DIR, "index.json")

    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    else:
        manifest = {"last_updated": None, "reports": []}

    manifest["reports"] = [
        r for r in manifest["reports"]
        if not (r["type"] == report_type and r["date"] == date_str)
    ]

    manifest["reports"].append({
        "type": report_type,
        "date": date_str,
        "file": filename,
        "article_count": article_count,
    })

    manifest["reports"].sort(key=lambda r: r["date"], reverse=True)
    manifest["last_updated"] = datetime.now().isoformat()

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def update_dashboard_data(analysis, date_str):
    """data/dashboard-data.json 갱신 — 뉴스 분석 결과 반영"""
    data_path = os.path.join(DATA_DIR, "dashboard-data.json")
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(data_path):
        with open(data_path, "r", encoding="utf-8") as f:
            dashboard = json.load(f)
    else:
        dashboard = {}

    today = datetime.strptime(date_str, "%Y-%m-%d")
    d_day = (ELECTION_DATE - today).days

    dashboard["last_updated"] = date_str
    dashboard["election_date"] = "2026-06-03"
    dashboard["header"] = {
        "update_date": date_str.replace("-", "."),
        "d_day": d_day,
        "voters": "~45만 명"
    }

    # 감성분석
    sentiment = {}
    for name in CANDIDATE_NAMES:
        s = analysis["candidate_sentiment"][name]
        if s["total"] > 0:
            pos_pct = round(s["pos"] / s["total"] * 100)
            neg_pct = round(s["neg"] / s["total"] * 100)
            neu_pct = 100 - pos_pct - neg_pct
            score = pos_pct - neg_pct
            sentiment[name] = {
                "positive": pos_pct,
                "neutral": max(0, neu_pct),
                "negative": neg_pct,
                "score": score
            }
    if sentiment:
        dashboard["sentiment"] = sentiment

    # 이슈 관심도
    issue_data = analysis["issue_counter"]
    max_count = max(issue_data.values()) if issue_data and max(issue_data.values()) > 0 else 1
    dashboard["issue_interest"] = {
        "labels": list(issue_data.keys()),
        "data": [round(count / max_count * 100) for count in issue_data.values()]
    }

    # 언론 노출도
    mention_counts = {name: 0 for name in CANDIDATE_NAMES}
    for m in analysis["candidate_mentions"]:
        mention_counts[m["name"]] = m["count"]
    max_mentions = max(mention_counts.values()) if mention_counts and max(mention_counts.values()) > 0 else 1
    dashboard["media_exposure"] = {
        name: round(count / max_mentions * 100)
        for name, count in mention_counts.items()
        if count > 0
    }

    # 소셜미디어 레이더 — 언론노출 값만 갱신
    if "social_radar" not in dashboard:
        dashboard["social_radar"] = {
            "조성환": [40, 45, 40, 55, 40, 30],
            "김경일_추정": [65, 60, 55, 60, 60, 50]
        }
    jsh_exposure = dashboard["media_exposure"].get("조성환", 30)
    dashboard["social_radar"]["조성환"][5] = jsh_exposure

    # 경쟁력 레이더 — 언론노출 값만 갱신
    if "competitiveness_radar" not in dashboard:
        dashboard["competitiveness_radar"] = {
            "조성환": [90, 95, 80, 25, 35, 50, 92, 78]
        }
    dashboard["competitiveness_radar"]["조성환"][4] = jsh_exposure

    # collection_status
    if "collection_status" not in dashboard:
        dashboard["collection_status"] = {}
    dashboard["collection_status"]["news_last_success"] = datetime.now().isoformat()
    dashboard["collection_status"]["news_articles_collected"] = sum(
        m["count"] for m in analysis["candidate_mentions"]
    )

    # sentiment_details
    if "sentiment_details" not in dashboard:
        dashboard["sentiment_details"] = {}
    for name in CANDIDATE_NAMES:
        s = analysis["candidate_sentiment"][name]
        if s["total"] > 0:
            pos_pct = round(s["pos"] / s["total"] * 100)
            neg_pct = round(s["neg"] / s["total"] * 100)
            details = dashboard["sentiment_details"].get(name, {})
            details.update({
                "positive": pos_pct,
                "neutral": max(0, 100 - pos_pct - neg_pct),
                "negative": neg_pct,
                "score": pos_pct - neg_pct,
                "article_count": s["total"],
            })
            if "sample_positive" not in details:
                details["sample_positive"] = []
            if "sample_negative" not in details:
                details["sample_negative"] = []
            dashboard["sentiment_details"][name] = details

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    print(f"[완료] dashboard-data.json 갱신: D-{d_day}, 감성분석 {len(sentiment)}명, 이슈 {len(issue_data)}개")


def main():
    parser = argparse.ArgumentParser(description="파주시장 선거 뉴스 수집")
    parser.add_argument("--type", choices=["hourly", "weekly", "monthly"], required=True)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()

    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("오류: NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 환경변수를 설정하세요.", file=sys.stderr)
        sys.exit(1)

    report_date = datetime.strptime(args.date, "%Y-%m-%d")

    if args.type == "hourly":
        period_start = report_date - timedelta(days=1)
        period_end = report_date.replace(hour=23, minute=59, second=59)
    elif args.type == "weekly":
        period_start = report_date - timedelta(days=7)
        period_end = report_date.replace(hour=23, minute=59, second=59)
    else:
        period_start = report_date.replace(day=1) - timedelta(days=1)
        period_start = period_start.replace(day=1)
        period_end = report_date.replace(hour=23, minute=59, second=59)

    period_start = period_start.astimezone() if period_start.tzinfo else period_start
    period_end = period_end.astimezone() if period_end.tzinfo else period_end

    print(f"[정보] {args.type} {'데이터 갱신' if args.type == 'hourly' else '보고서 생성'}: {period_start.date()} ~ {period_end.date()}")
    print(f"[정보] 키워드 {len(ALL_KEYWORDS)}개로 검색 시작...")

    articles = collect_articles(client_id, client_secret, ALL_KEYWORDS, period_start, period_end)
    print(f"[정보] 수집 기사: {len(articles)}건")

    analysis = analyze_articles(articles)

    update_dashboard_data(analysis, args.date)

    if args.type == "hourly":
        print(f"[완료] hourly 대시보드 갱신 완료 ({len(articles)}건 분석)")
        return

    report = build_report(args.type, args.date, period_start, period_end, articles, analysis)

    type_dir = os.path.join(REPORTS_DIR, args.type)
    os.makedirs(type_dir, exist_ok=True)

    filename = f"{args.type}/{args.date}.json"
    filepath = os.path.join(REPORTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    update_manifest(args.type, args.date, filename, len(articles))

    print(f"[완료] 보고서 저장: {filepath}")


if __name__ == "__main__":
    main()
