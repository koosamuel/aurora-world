# U20 · 합성 디지털 샘플링 입력 준비

U20은 원화·요구 명세·버전과 현행 측정 **입력**을 다룹니다. U21의 규칙 기하 생성·공개 형상 변환은 [생성 문서](GENERATION.md)에 구현 범위를 기록했습니다. 사전학습2D는 [AI 경로](AI_SAMPLING.md), 합성 U22 검토/승인은 [검토 경로](SAMPLE_REVIEWS.md)에 추가했습니다. 실제 사용자/현업 승인, 패턴/BOM 연결(U23), 현행 대비 효과 분석(U24)은 후속입니다. 처리 완료를 승인/생성/절감 성공으로 바꾸지 않습니다.

## 실행·화면

```sh
PYTHONPATH=src python3 -m aurora serve --port 8765
PYTHONPATH=src python3 -m aurora sampling --input configs/examples/sampling/01-bunny-v1.json --output results/sampling-bunny-v1-new
```

두 번째 **디지털 샘플링·라벨링** 탭 상단에서 제품·버전·원화를 확인합니다. 로컬에서는 최신 명세의 `수정본 만들기` → 치수/원단/필수 조건 편집 → `입력 검증` → `검증 명세 등록`으로 진행합니다. 값을 바꾸면 검증을 다시 해야 합니다. 이전 버전은 읽기 전용으로 보존합니다. 원화·색상·현행 사건·출처는 `명세 JSON 받기`의 형식대로 파일을 준비해 `합성 명세 JSON 파일`로 검증·등록할 수 있습니다. 자체 서명/암호화나 기업 자료 업로드를 제공하는 기능은 아닙니다.

- 로컬: `results/sampling-briefs.sqlite3`에 불변 버전을 저장합니다. 로컬 재시작/새로고침 후에도 유지됩니다. 로그인 없는 loopback 개발 도구입니다.
- GitHub Pages: 저장된 합성 명세 12개를 조회·다운로드합니다. 파일 검증/등록/수정 버튼은 비활성입니다. 실제 Supabase 저장으로 표시하지 않습니다.
- 기존 수요예측·라벨링·제품 ID 감사의 데이터와 실행은 그대로 분리합니다. `#/labeling` 주소와 두 탭을 유지합니다.
- CLI 출력: `brief.json`, `validation.json`, `artwork.svg`, `artifacts.json`(크기/SHA-256). 출력은 새 폴더만 허용합니다. 실패는 종료1이며 기존 결과를 덮어쓰지 않습니다.

## 합성 자료와 참고 범위

`tools/build_sampling_demo.py`로 토끼·젖소·둥근 강아지·고양이·선인장형·과일형의 **6개 제품×명세2버전=12개**를 재현합니다. 각 원화는 독립적인 기하 도형으로 그렸습니다. 사용자가 제공한 상품/브랜드 소개 화면의 일반적 동물·자세·색상·둥근 형태를 참고했으며 회사 사진·로고·캐릭터 도안을 파일에 넣지 않았습니다. 치수·원단·필수 조건·제작/BOM 사건은 전부 가상이며 실제 상품 측정값이 아닙니다.

명세 변경과 원화 변경은 별개입니다. 기본 v2는 요구 높이/조건을 바꾸고 같은 개념 원화 v1을 사용합니다. 그림이 실제 크기/물리/봉제 특성을 증명하지 않습니다. 4제품은 가상 현행 기록, 2제품은 미측정 예제를 포함합니다. 제작 사건2건에서 총3개를 기록한 가상 기준과 경과336시간, BOM 오류 수정1건/설계 변경1건은 소프트웨어 입력 사례입니다. DS 효과 측정/회사 절감 실적이 아닙니다. 미측정 값은 null로 유지하고 명시적으로 기록한 0과 구분합니다.

```sh
PYTHONPATH=src python3 tools/build_sampling_demo.py
```

재생성은 예시 계약 파일과 Pages 카탈로그를 갱신합니다. 등록된 로컬 버전은 자동 변경하지 않습니다. 이미 등록된 버전과 파일 내용이 달라지면 시작 시 충돌을 확인해야 하므로 기존 명세를 수정해 같은 버전으로 배포하지 말고 새 버전/제품을 준비하세요.

## 입력 계약 v1

스키마 `aurora-sampling-brief-v1`, `data_kind=synthetic`, JSON 최대512 KiB. 필수 필드는 예제 파일과 같습니다. 알 수 없는 필드·중복 JSON 키·잘못된 타입·비유한 수는 거부합니다.

- 제품: `SYN-` 접두 제품 ID, 이름, 양의 정수 `brief_version`/`artwork_version`, 이전 명세의 canonical JSON SHA-256 `previous_checksum`.
- 원화: basename `.svg`, media_type, SVG 문자열, UTF-8 SHA-256, 캔버스 mm·viewBox. 회사 파일을 받는 범용 SVG 업로더가 아닙니다. v1은 단순 svg/g/ellipse/circle/rect/path와 제한된 기하/색상 속성만 허용합니다. script·외부 image/href·이벤트/CSS·DTD/엔티티·과도한 복잡도·잘못된 경로 인수를 거부합니다. 원화 캔버스 크기와 제품 목표 치수는 다른 개념입니다.
- 요구: 양수 높이/너비/깊이·mm 또는 cm, 가상 원단 코드/설명, 부위별 이름/hex 색상, 필수 조건. 정규화 요약은 mm를 Decimal 문자열로 제공합니다.
- 출처: `source_type=self_generated_synthetic`, `company_data=false`, `allowed_use=public_synthetic_demo`, 설명. 이 값은 입력자의 출처 선언이며 자동 권리 검증이 아닙니다. 회사 자료나 public/mixed 입력은 이 v1에 등록하지 않습니다.
- 현행 입력: `unmeasured` 또는 `synthetic_recorded`, 관측창, 기간 정의, UTC 시작/종료, 실제 제작을 가정한 사건 ID/시각/수량, BOM 변경 사건/시각/사유. 모든 날짜/사건은 창·개발기간 안에 있어야 합니다. 사건 ID 중복·역전·잘못된 양/사유를 거부합니다. `unmeasured`는 측정값/사건을 넣을 수 없습니다. 오류 수정과 설계 변경을 따로 셉니다.

## 불변 등록·버전 충돌

같은 제품·버전·체크섬 재등록은 기존 결과를 재사용합니다. 같은 제품·버전의 다른 내용은409입니다. 새 명세는 최신 버전+1과 해당 부모 해시가 필요합니다. 원화 내용/메타데이터가 바뀌면 원화 버전도+1, 같으면 원화 버전을 유지합니다. SQLite 트랜잭션이 동시에 들어오는 서로 다른 수정본 중 하나만 허용합니다. 이 동작은 등록 데이터의 일관성이며 현업 승인/검수 이력 구현이 아닙니다.

## 로컬 API

| 경로 | 동작 |
|---|---|
| GET `/api/sampling/briefs` | 모든 등록 버전의 요약·해시 |
| GET `/api/sampling/briefs/{product_id}/{version}` | 불변 명세·요약·등록시각 |
| POST `/api/sampling/validate` | 파일/필드 검증·mm 정규화·요약, 저장 안 함 |
| POST `/api/sampling/briefs` | 서버 재검증·부모/버전 확인 후 로컬 등록 |

Host는 loopback만, POST Origin은 같은 출처만 허용합니다. 브라우저/임의 파일의 코드를 실행하지 않고 URL로 원화·외부 AI를 불러오지 않습니다. Supabase 테이블·RPC·RLS·클라우드 워커는 이번 U20에 맞춰 변경하지 않았습니다. 원격 U20 등록과 회사 IP 허용 환경은 후속입니다.

## 검증

12개 단위 검사는 합성 계약/단위·미측정/0·현행 사건·안전한 SVG/해시·버전/부모·동시 등록·재현/CLI를 확인합니다. 실제 로컬 HTTP에서 검증/등록·409 충돌·중복 JSON·크기·Host/Origin·경로를 확인했습니다. 브라우저는 수정→검증→등록→복원·이전 버전 보존·편집 시 재검증·파일 검증/중복 등록·미측정·모바일·기존 분류·정적 모드를 검사합니다.

```sh
PYTHONPATH=src python3 -m unittest tests.test_sampling -v
AURORA_TEST_URL=http://127.0.0.1:8765 node tests/test_sampling_ui.mjs
```
