# Nasdaq 50 Daily Shorts

한국시간 기준 전날 발생한 나스닥 연관 이슈를 기존 단타 봇의 50종목에 매핑하고, 이슈당 60초 세로형 쇼츠로 렌더링합니다.

## 조회수 높은 쇼츠에서 적용한 구조

- 첫 1.5초에 인사 없이 결과·위기 제시
- 4초 안에 공식 수치와 마지막까지 볼 이유 제시
- 한 영상에 하나의 인과관계만 설명
- 18초에 “하지만” 반전으로 두 번째 훅 구성
- 37초에 50종목 5×10 히트맵으로 큰 패턴 전환
- 49초에 판단이 틀릴 조건을 제시해 신뢰 확보
- 마지막 문장을 첫 문장과 연결해 자연스러운 재생 루프 구성
- CTA는 한 가지만 사용

참고 사례와 원칙:

- YouTube 공식 Shorts 조회수 변경: https://support.google.com/youtube/answer/10059070?hl=en
- YouTube 공식 시청지속시간 분석: https://support.google.com/youtube/answer/9314415?hl=en
- Mark Tilbury, `You'll NEVER Own A Home Unless...`: https://www.youtube.com/shorts/rNCCyer1onA
- Humphrey Yang, `Why Stock Prices Don't Matter!`: https://www.youtube.com/shorts/65ciWFjXaq8
- Humphrey Yang, `What Is Short Selling?`: https://www.youtube.com/shorts/rLk5AOr39JU

공개 조회수는 채널 규모·게시 기간·유료 유입의 영향도 받으므로 특정 편집 방식의 인과 효과로 단정하지 않습니다.

## 설치

```bash
uv pip install --python .venv/Scripts/python.exe -e '.[shorts]'
```

## 입력

- 50종목: `config/shorts_50_universe.json`
- 날짜별 이슈: `shorts/YYYY-MM-DD/issues.json`
- 각 이슈에는 사실, 출처, 긍정·관찰·위험 매핑, 9개 장면 대본이 필요합니다.

## 렌더링

```bash
.venv/Scripts/python.exe scripts/render_shorts.py \
  --issues shorts/2026-07-15/issues.json \
  --universe config/shorts_50_universe.json
```

생성 파일:

```text
shorts/YYYY-MM-DD/
  issues.json
  manifest.json
  <slug>.mp4
  <slug>.srt
  <slug>_script.md
  assets/<slug>/
    scene_*.png
    narration.mp3
    narration_60s.m4a
    visuals.mp4
```

## 리밸런싱 연결

뉴스만으로 매수·매도를 결정하지 않습니다.

1. 50종목 전체에서 전날 이슈를 긍정·관찰·위험·중립으로 분류
2. `latest_candidates.csv`의 기존 상위 3종목과 이슈 위험군의 중첩 확인
3. 기존 점수, 달러 거래대금, RSI, 손절 조건을 그대로 적용
4. 이슈의 반증 조건이 확인되면 매핑 갱신

## YouTube 자동 업로드

OAuth 설정과 자동 업로드 방법은 [`YOUTUBE_UPLOAD_SETUP.md`](YOUTUBE_UPLOAD_SETUP.md)를 참고하세요.

```bash
# 인증 없이 최신 완성본 점검
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --dry-run

# 첫 비공개 영상 1편 업로드
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --limit 1
```

성공한 영상은 날짜 폴더의 `youtube_upload_state.json`에 기록돼 재실행 시 중복 업로드되지 않습니다.

## 업로드 후 확인 지표

- Viewed vs swiped away
- Engaged views
- 평균 시청 지속시간·평균 시청 비율
- 0~3초 이탈
- 18~27초 반전 구간 dip/spike
- 37~49초 히트맵 구간 이탈
- 마지막 5초 재시청 구간

본 콘텐츠는 정보 제공 목적이며 투자 권유가 아닙니다.
