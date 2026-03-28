from flask import Flask, render_template, request, jsonify
import os, math, requests, re
from collections import Counter
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
import isodate

load_dotenv()
app = Flask(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YT_BASE = "https://www.googleapis.com/youtube/v3"

# =====================
# 기존 기능 1: 메인 페이지
# =====================
@app.route("/")
@app.route("/trends")
def home():
    return render_template("index.html")

# =====================
# 기존 기능 2: 유튜브 검색 및 점수 계산 엔진
# =====================
def yt_search_video_ids(query: str, published_after_iso: str, max_results=50):
    params = {
        "key": YOUTUBE_API_KEY, "part": "snippet", "type": "video",
        "q": query, "maxResults": max_results, "order": "viewCount",
        "publishedAfter": published_after_iso, "regionCode": "KR"
    }
    r = requests.get(f"{YT_BASE}/search", params=params, timeout=30)
    r.raise_for_status()
    return [item["id"]["videoId"] for item in r.json().get("items", []) if "videoId" in item.get("id", {})]

def yt_videos(video_ids):
    out = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        params = {"key": YOUTUBE_API_KEY, "part": "snippet,contentDetails,statistics", "id": ",".join(chunk)}
        r = requests.get(f"{YT_BASE}/videos", params=params, timeout=30)
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out

def yt_channels(channel_ids):
    out = []
    channel_ids = list(set(cid for cid in channel_ids if cid))
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i:i+50]
        params = {"key": YOUTUBE_API_KEY, "part": "statistics", "id": ",".join(chunk)}
        r = requests.get(f"{YT_BASE}/channels", params=params, timeout=30)
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out

def traffic_score(vph, like_rate, comment_rate):
    return (0.65 * math.log10(1 + max(vph, 0.0)) + 0.25 * (max(like_rate, 0.0) * 100) + 0.10 * (max(comment_rate, 0.0) * 1000))

def replication_score(view_sub_ratio, vph, like_rate):
    return (0.55 * math.log10(1 + max(view_sub_ratio, 0.0)) + 0.35 * math.log10(1 + max(vph, 0.0)) + 0.10 * (max(like_rate, 0.0) * 100))

@app.route("/api/trends", methods=["POST"])
def api_trends():
    if not YOUTUBE_API_KEY:
        return jsonify({"error": ".env 파일에 YOUTUBE_API_KEY를 설정해주세요."}), 400

    data = request.json or {}
    query = (data.get("query") or "").strip()
    days = int(data.get("days") or 3)
    min_views = int(data.get("min_views") or 5000)
    sort_by = (data.get("sort_by") or "final").strip()
    duration_filter = data.get("duration", "shorts")

    if not query:
        return jsonify({"error": "검색어를 입력해주세요."}), 400

    try:
        now = datetime.now(timezone.utc)
        published_after = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")

        ids = yt_search_video_ids(query, published_after, max_results=50)
        if not ids: return jsonify({"rows": []})

        vids = yt_videos(ids)
        channel_ids = [v.get("snippet", {}).get("channelId") for vids in vids]
        ch_items = yt_channels(channel_ids)
        subs_map = {c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0) or 0) for c in ch_items}

        rows = []
        for v in vids:
            sn = v.get("snippet", {})
            st = v.get("statistics", {})
            cd = v.get("contentDetails", {})

            dur_str = cd.get("duration", "PT0S")
            dur_sec = isodate.parse_duration(dur_str).total_seconds()
            
            if duration_filter == "shorts" and dur_sec > 65: continue
            elif duration_filter == "under_5m" and (dur_sec <= 65 or dur_sec > 300): continue
            elif duration_filter == "over_10m" and dur_sec < 600: continue

            views = int(st.get("viewCount", 0) or 0)
            if views < min_views: continue

            likes = int(st.get("likeCount", 0) or 0)
            comments = int(st.get("commentCount", 0) or 0)
            published_at = isoparse(sn.get("publishedAt"))
            age_hours = max((now - published_at).total_seconds() / 3600.0, 0.2)

            vph = views / age_hours
            like_rate = (likes / views) if views > 0 else 0.0
            comment_rate = (comments / views) if views > 0 else 0.0

            channel_id = sn.get("channelId")
            subs = subs_map.get(channel_id, 0)
            view_sub_ratio = (views / subs) if subs > 0 else float(views)

            ts = traffic_score(vph, like_rate, comment_rate)
            rs = replication_score(view_sub_ratio, vph, like_rate)
            fs = ts * 0.55 + rs * 0.45

            vid = v["id"]
            rows.append({
                "title": sn.get("title", ""),
                "video_url": f"https://www.youtube.com/watch?v={vid}",
                "channel_title": sn.get("channelTitle", ""),
                "channel_url": f"https://www.youtube.com/channel/{channel_id}" if channel_id else "",
                "views": views,
                "likes": likes,
                "views_per_hour": round(vph, 2),
                "view_sub_ratio": round(view_sub_ratio, 2),
                "traffic_score": round(ts, 2),
                "replication_score": round(rs, 2),
                "final_score": round(fs, 2),
                "published_at": (published_at + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
            })

        key_map = {"traffic": "traffic_score", "replication": "replication_score", "final": "final_score"}
        sort_key = key_map.get(sort_by, "final_score")
        rows.sort(key=lambda x: x.get(sort_key, 0), reverse=True)

        return jsonify({"rows": rows})
    except Exception as e:
        return jsonify({"error": f"서버 오류: {str(e)}"}), 500

# =====================
# ⭐ 신규 기능: 실시간 유튜브 핫이슈 단어 탐색기 (새로운 주소: /hot-trends)
# =====================
@app.route("/hot-trends")
def hot_trends():
    if not YOUTUBE_API_KEY:
        return "에러: 유튜브 API 키가 설정되지 않았습니다."

    url = f"{YT_BASE}/videos"
    params = {
        "part": "snippet,statistics",
        "chart": "mostPopular",
        "regionCode": "KR",
        "videoCategoryId": "25",
        "maxResults": 30,
        "key": YOUTUBE_API_KEY
    }

    try:
        response = requests.get(url, params=params)
        data = response.json()

        video_html = "<h2>📺 실시간 인기 급상승 뉴스/정치 영상</h2><ul>"
        all_titles = ""

        for item in data.get("items", []):
            title = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            views = item["statistics"].get("viewCount", "0")

            video_html += f"<li style='margin-bottom:10px;'><b>{title}</b><br>(채널: {channel} | 조회수: {views}회)</li>"
            all_titles += title + " "

        video_html += "</ul>"

        stop_words = ['뉴스', '알고', '보니', '진짜', '이유', '어떻게', '결국', '이런', '저런', '있는', '하는', '그리고', '그래서', '속보', '단독', '충격', '오늘', '지금', '너무', '정말', '대박', '아니', '그냥', '무슨', '어떤', '왜', '대한', '모두']
        words = re.findall(r'[가-힣]{2,}', all_titles)
        filtered_words = [word for word in words if word not in stop_words]
        
        word_counts = Counter(filtered_words)
        top_words = word_counts.most_common(10)

        word_html = "<h2>🎯 지금 당장 터지고 있는 핵심 키워드 TOP 10</h2><ol style='color: #d32f2f;'>"
        for word, count in top_words:
            word_html += f"<li><b>{word}</b> ({count}회 등장)</li>"
        word_html += "</ol>"

        final_html = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <title>우파 쇼츠 트렌드 탐색기</title>
        </head>
        <body style="font-family: 'Malgun Gothic', sans-serif; padding: 30px; line-height: 1.6;">
            <h1>🚀 실시간 트렌드 탐색기 엔진 (불용어 필터 적용)</h1>
            <p>유튜브 알고리즘이 밀어주는 최신 뉴스 데이터를 분석합니다.</p>
            <hr style="border: 2px solid #333;">
            {word_html}
            <hr style="border: 1px solid #ccc;">
            {video_html}
        </body>
        </html>
        """
        return final_html

    except Exception as e:
        return f"데이터를 불러오는 중 에러가 발생했습니다: {str(e)}"

# =====================
# 실행
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)