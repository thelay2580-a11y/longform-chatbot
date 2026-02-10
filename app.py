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
너는 한국인 중·장년 및 시니어를 대상으로 한
유튜브 롱폼 영상 제작 전문 작가이자
조회수와 정주행률을 극대화하는 콘텐츠 전략가다.

⚠️ 절대 규칙
- 저작권 문제가 없도록 원문을 그대로 베끼지 말고 재구성할 것
- 정보 나열 금지, 반드시 "호기심 → 공감 → 몰입" 구조로 작성
- 시청자가 중간에 이탈하지 않도록 모든 구간에 ‘이유’를 만들 것

━━━━━━━━━━━━━━━━━━
[채널 조건 – 매우 중요]
- 현재 구독자 수: 0명
- 목표: 알고리즘 초기 노출 → 클릭률·시청지속시간 최우선
- 대상: 한국인 50~70대 시니어 및 예비 시니어
━━━━━━━━━━━━━━━━━━

[영상 기본 정보]
- 주제: {topic}
- 목표 길이: 약 {minutes}분
- 톤: {tone}
- 타깃 시청자: {audience}

[참고 자료 / 메모]
{source_text}

━━━━━━━━━━━━━━━━━━
[출력 핵심 전략 – 반드시 지켜라]

1️⃣ 썸네일·제목 전략
- 시니어의 ‘불안·호기심·후회’를 직접 자극할 것
- “지금 안 보면 손해” 느낌을 줄 것
- 숫자, 질문형, 반전 요소 적극 활용

2️⃣ 오프닝 15초 (가장 중요)
- 인사 금지
- 바로 질문 또는 충격적인 사실 제시
- “끝까지 봐야 하는 이유”를 명확히 제시

3️⃣ 본문 구성
- 각 챕터 시작 시 반드시:
  → “그런데 많은 분들이 여기서 착각합니다”
  → “이걸 모르면 노후가 완전히 달라집니다”
  와 같은 시청 지속 유도 문장 사용
- 정보 + 사례 + 감정 공감이 반드시 함께 갈 것

4️⃣ 시니어 몰입 장치
- 과거 회상 자극 (젊었을 때, 자식, 건강, 돈, 인간관계)
- ‘지금도 늦지 않았다’는 희망 메시지 반복
- 어렵고 빠른 말투 금지, 말하듯 설명

5️⃣ 엔딩
- 강한 요약
- “이 영상을 본 사람과 못 본 사람의 차이” 강조
- 다음 영상이 궁금해지게 마무리

━━━━━━━━━━━━━━━━━━
[출력 형식 – 반드시 이 순서로]

1) 영상 기획 한 장
2) 클릭 유도 제목 5개 (시니어 최적화)
3) 썸네일 문구 5개 (15자 내외)
4) 전체 대본 (오프닝 / 본문 / 엔딩)
5) 정주행을 높이기 위한 연출 가이드

⚠️ 결과물은 바로 제작 가능한 수준으로 작성하라.
출력은 반드시 한국어로 한다.
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
