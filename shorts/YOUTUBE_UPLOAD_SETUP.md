# YouTube 자동 업로드 설정

완성된 `shorts/YYYY-MM-DD/*.mp4`를 YouTube Data API v3로 중복 없이 업로드합니다. 기본값은 **비공개(private)**이며, 한국어 SRT 자막과 선택적 재생목록을 함께 등록합니다.

## 사용자가 준비하거나 결정할 정보

필수 항목은 세 가지입니다.

1. **Google OAuth 데스크톱 앱 JSON 파일**
   - 저장 위치: `config/youtube_client_secret.json`
   - JSON 안의 값을 채팅이나 소스 코드에 붙여 넣지 마세요.
2. **아동용 콘텐츠 여부**
   - 일반 주식 뉴스라면 보통 `made_for_kids: false`이지만 채널 운영자가 직접 확인해야 합니다.
3. **공개 범위**
   - 최초 테스트 권장값: `private`
   - 가능한 값: `private`, `unlisted`, `public`

선택 항목:

- `playlist_id`: 자동으로 넣을 YouTube 재생목록 ID. 사용하지 않으면 빈 문자열
- `notify_subscribers`: 공개 업로드 시 구독자 알림 여부
- `default_tags`: 공통 태그

YouTube 채널 ID, 이메일, 비밀번호, API 키는 설정 파일에 입력하지 않습니다. 첫 실행 시 브라우저에서 원하는 Google 계정과 YouTube 채널을 선택합니다.

## 1. Google Cloud 설정

1. https://console.cloud.google.com/ 에서 프로젝트를 만듭니다.
2. **API 및 서비스 → 라이브러리**에서 `YouTube Data API v3`를 활성화합니다.
3. **OAuth 동의 화면**을 구성합니다.
4. 앱이 테스트 상태라면 업로드에 사용할 Google 계정을 **테스트 사용자**로 추가합니다.
5. **사용자 인증 정보 만들기 → OAuth 클라이언트 ID**를 선택합니다.
6. 애플리케이션 유형은 **데스크톱 앱**으로 선택합니다.
7. JSON을 내려받아 다음 이름으로 저장합니다.

```text
E:\python\shot_bot\config\youtube_client_secret.json
```

공식 문서:

- 업로드 가이드: https://developers.google.com/youtube/v3/guides/uploading_a_video
- `videos.insert`: https://developers.google.com/youtube/v3/docs/videos/insert

> 2020-07-28 이후 생성된 미확인 API 프로젝트는 API로 업로드한 영상이 비공개로 제한될 수 있습니다. 공개 제한을 해제하려면 Google의 YouTube API 규정 준수 감사를 받아야 할 수 있습니다.

## 2. 설정 파일 만들기

Git Bash에서 실행합니다.

```bash
cp config/youtube_upload.example.json config/youtube_upload.json
```

`config/youtube_upload.json`에서 다음 값만 확인하거나 수정합니다.

```json
{
  "client_secrets_file": "config/youtube_client_secret.json",
  "token_file": "config/youtube_token.json",
  "privacy_status": "private",
  "made_for_kids": false,
  "category_id": "25",
  "default_tags": ["나스닥", "미국주식", "주식이슈", "경제뉴스"],
  "playlist_id": "",
  "notify_subscribers": false,
  "upload_captions": true,
  "language": "ko"
}
```

`youtube_client_secret.json`, `youtube_token.json`, 실제 설정 파일과 업로드 상태 파일은 Git에서 제외됩니다.

## 3. 의존성 설치

```bash
uv pip install --python .venv/Scripts/python.exe -e '.[youtube-upload]'
```

## 4. 업로드 전 점검

OAuth 인증이나 API 호출 없이 최신 날짜 폴더를 검사합니다.

```bash
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --dry-run
```

특정 날짜:

```bash
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --date 2026-07-15 \
  --dry-run
```

## 5. 첫 실제 업로드

먼저 한 편만 비공개로 시험합니다.

```bash
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --date 2026-07-15 \
  --limit 1
```

첫 실행 시 브라우저가 열립니다. 업로드할 YouTube 채널의 Google 계정을 선택하고 권한을 승인합니다. 승인 결과는 `config/youtube_token.json`에 저장돼 다음 실행부터 브라우저 로그인이 생략됩니다.

한 편을 YouTube Studio에서 확인한 뒤 전체를 올립니다.

```bash
.venv/Scripts/python.exe scripts/upload_youtube_shorts.py \
  --config config/youtube_upload.json \
  --date 2026-07-15
```

`--date`를 생략하면 `manifest.json`이 있는 최신 날짜 폴더를 자동 선택합니다.

## 중복 업로드 방지

성공한 영상 ID와 URL은 다음 파일에 즉시 저장됩니다.

```text
shorts/YYYY-MM-DD/youtube_upload_state.json
```

같은 명령을 다시 실행해도 이미 성공한 `slug`는 건너뜁니다. 영상 업로드는 8MB 청크의 재개 가능한 방식이며 HTTP 500·502·503·504 오류는 지수 간격으로 최대 5회 재시도합니다.
