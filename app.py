from flask import Flask, render_template, request, jsonify
import os, math, requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from dateutil.parser import isoparse
import isodate

# 환경변수(.env) 불러오기
load_dotenv()
app = Flask(__name__)

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YT_BASE = "https://www.googleapis.com/youtube/v3"

@app.route("/")
@app.route("/trends")
def home():
    return render_template("index.html")

# 1. 유튜브 검색 함수 (키워드로 영상 ID 수집)
def yt_search_video_ids(query: str, published_after_iso: str, max_results=50):
    params = {
        "key": YOUTUBE_API_KEY, "part": "snippet", "type": "video",
        "q": query, "maxResults": max_results, "order": "viewCount",
        "publishedAfter": published_after_iso, "regionCode": "KR"
    }
    r = requests.get(f"{YT_BASE}/search", params=params, timeout=30)
    r.raise_for_status()
    return [item["id"]["videoId"] for item in r.json().get("items", []) if "videoId" in item.get("id", {})]

# 2. 영상 상세 정보(조회수, 좋아요, 길이 등) 가져오기
def yt_videos(video_ids):
    out = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        params = {
            "key": YOUTUBE_API_KEY,
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(chunk)
        }
        r = requests.get(f"{YT_BASE}/videos", params=params, timeout=30)
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out

# 3. 채널 정보(구독자 수) 가져오기
def yt_channels(channel_ids):
    out = []
    channel_ids = list(set(cid for cid in channel_ids if cid))
    for i in range(0, len(channel_ids), 50):
        chunk = channel_ids[i:i+50]
        params = {
            "key": YOUTUBE_API_KEY, "part": "statistics", "id": ",".join(chunk)
        }
        r = requests.get(f"{YT_BASE}/channels", params=params, timeout=30)
        r.raise_for_status()
        out.extend(r.json().get("items", []))
    return out

# 4. 트래픽 폭발 점수 (시간당 조회수, 좋아요 비율 등)
def traffic_score(vph, like_rate, comment_rate):
    return (0.65 * math.log10(1 + max(vph, 0.0)) +
            0.25 * (max(like_rate, 0.0) * 100) +
            0.10 * (max(comment_rate, 0.0) * 1000))

# 5. 신인 재현 점수 (구독자 대비 조회수 등)
def replication_score(view_sub_ratio, vph, like_rate):
    return (0.55 * math.log10(1 + max(view_sub_ratio, 0.0)) +
            0.35 * math.log10(1 + max(vph, 0.0)) +
            0.10 * (max(like_rate, 0.0) * 100))

# ============================
# 진짜 트렌드 탐색 API
# ============================
@app.route("/api/trends", methods=["POST"])
def api_trends():
    if not YOUTUBE_API_KEY:
        return jsonify({"error": ".env 파일에 YOUTUBE_API_KEY를 설정해주세요."}), 400

    data = request.json or {}
    query = (data.get("query") or "").strip()
    days = int(data.get("days") or 3)
    min_views = int(data.get("min_views") or 5000)
    sort_by = (data.get("sort_by") or "final").strip()

    if not query:
        return jsonify({"error": "검색어를 입력해주세요."}), 400

    try:
        now = datetime.now(timezone.utc)
        published_after = (now - timedelta(days=days)).isoformat().replace("+00:00", "Z")

        # 1. API 호출: 후보 영상 검색
        ids = yt_search_video_ids(query, published_after, max_results=50)
        if not ids:
            return jsonify({"rows": []})

        # 2. API 호출: 상세 정보
        vids = yt_videos(ids)

        # 3. API 호출: 채널 구독자
        channel_ids = [v.get("snippet", {}).get("channelId") for v in vids]
        ch_items = yt_channels(channel_ids)
        subs_map = {c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0) or 0) for c in ch_items}

        rows = []
        for v in vids:
            sn = v.get("snippet", {})
            st = v.get("statistics", {})
            cd = v.get("contentDetails", {})

            # 쇼츠 필터 (길이가 65초 이하인 것만 취급)
            dur_str = cd.get("duration", "PT0S")
            dur_sec = isodate.parse_duration(dur_str).total_seconds()
            if dur_sec > 65:  
                continue

            views = int(st.get("viewCount", 0) or 0)
            if views < min_views:
                continue

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
                "published_at": (published_at + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M") # 한국시간 변환
            })

        # 정렬 처리
        key_map = {"traffic": "traffic_score", "replication": "replication_score", "final": "final_score"}
        sort_key = key_map.get(sort_by, "final_score")
        rows.sort(key=lambda x: x.get(sort_key, 0), reverse=True)

        return jsonify({"rows": rows})
        
    except Exception as e:
        return jsonify({"error": f"유튜브 데이터를 가져오는 중 오류가 발생했습니다: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)