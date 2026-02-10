from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
import os
from openai import OpenAI

# =====================
# 기본 설정
# =====================
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)

app = Flask(__name__)

# =====================
# 메인 페이지
# =====================
@app.route("/")
def home():
    return render_template("index.html")

# =====================
# 롱폼 프롬프트 생성기
# =====================
def build_longform_prompt(
    topic: str,
    source_text: str,
    minutes: int,
    tone: str,
    audience: str
):
    return f"""
너는 유튜브 롱폼 영상 제작 전문 작가다.
저작권 문제가 없도록, 원문을 그대로 베끼지 말고 재구성해서 작성하라.

[목표 영상 길이] {minutes}분
[톤] {tone}
[타깃 시청자] {audience}

[주제]
{topic}

[참고 자료/메모]
{source_text}

아래 형식으로 출력하라:

1) 영상 기획 한 장
2) 전체 대본(오프닝 / 본문 / 엔딩)
3) 화면 구성 / 연출 가이드
4) 제목 5개
5) 썸네일 문구 5개
""".strip()

# =====================
# 롱폼 생성 API
# =====================
@app.route("/generate", methods=["POST"])
def generate():
    data = request.json or {}

    topic = data.get("topic", "").strip()
    source_text = data.get("source_text", "")
    minutes = int(data.get("minutes", 10))
    tone = data.get("tone", "차분하고 설득력 있게")
    audience = data.get("audience", "대중")

    if not topic:
        return jsonify({"reply": "주제를 입력해 주세요"}), 400

    prompt = build_longform_prompt(
        topic, source_text, minutes, tone, audience
    )

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "출력은 한국어, 실무형으로."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7
    )

    return jsonify({
        "reply": response.choices[0].message.content
    })

# =====================
# 실행 (Render / Railway 대응)
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
