# U21 · 기하 디지털 샘플 생성과 방식 비교

U20의 불변 합성 명세를 읽어 **실제 glTF 2.0 GLB와 정면/측면 SVG**를 만든다. 규칙 기반 생성이며 학습한 확산모델·VAE·텍스트→이미지 모델을 실행하지 않는다. 현재 U21은 기하 기준선/공개 형상 변환과 데모를 구현한 상태다. 사전학습 2D 생성 방식·원화 해석·현업 품질 판정은 후속이다.

## 실행

```sh
PYTHONPATH=src python3 -m aurora serve --port 8765
PYTHONPATH=src python3 -m aurora generate --source u20:SYN-BUNNY:2 --seed 42 --output results/bunny-new
PYTHONPATH=src python3 -m aurora generate --source abo:B07JLZC571 --seed 42 --reference-root <ABO_디지털샘플링_선정> --output results/cushion-new
```

서버는 프로젝트 폴더의 `04_데이터/원본/공개연구데이터/ABO_디지털샘플링_선정`을 탐색하거나 `--reference-root`로 지정한 위치를 읽는다. Git 코드만 받은 환경에서는 합성 명세 생성과 Pages용 저장 결과 조회가 가능하다. ABO를 새로 변환하려면 별도로 내려받은 공식 원본과 `configs/sampling-references.json`의 해시가 일치해야 한다. 서버 실행 중 외부 URL·모델 다운로드·AI API 호출을 하지 않는다. 원본은 수정하지 않는다.

두 번째 **디지털 샘플링·라벨링** 탭의 U21에서 명세/시드 선택→2개 후보 생성→실제3D 회전/확대·옆면 보기→2D 투영·치수/시간 비교→해시 검사 후 다운로드로 진행한다. U20에서 등록한 새 명세 버전은 연결 목록에 반영된다. 기존 생성의 입력/해시/산출물은 바뀌지 않는다. U20 등록은 DS 입력 보존이며 샘플 승인과 다르다.

- 로컬: 제한 큐에서 새 계산 후 SQLite·결과 폴더에 저장. 브라우저 새로고침은 마지막 완료 실행을 복원한다.
- Pages: 6종 최신 U20 명세와 공개 쿠션3종, 입력9개×기준선/후보2개=18개 저장 결과를 비교한다. 새 시드/새 계산은 실행하지 않으며 버튼·모드에 구분한다.
- WebGL2를 지원하지 않으면 2D/GLB 다운로드를 이용한다. 실제3D 표시 실패를 생성/제작 성공으로 바꾸지 않는다.

## 생성 방식과 입력 경계

| 방식 | 입력·출력 | 미지원/구분 |
|---|---|---|
| ellipsoid-baseline-v1 | 같은 목표 치수의 단일 타원체, GLB·2D 투영 | 원화 재현/제작 가능한 형상이라는 주장이 아님 |
| part-geometry-v1 | U20의 BUNNY/COW/DOG/CAT/CACTUS/FRUIT 템플릿, 고정 seed로 몸통 비율 변형·부위 결합·목표 치수 정규화 | 임의 그림/문장의 의미 해석 없음. 색은 처음 두 색상+눈/잎 고정 팔레트; 원단 물성·모든 색상 조건은 사람 확인 |
| abo-fit-v1 | 공식 쿠션 GLB에 비균일 변환을 추가해 가상400×400×120mm로 조정. 원본 재질/텍스처 유지 | public형상+synthetic목표의 mixed 자료. 실제 상품 실측/봉제완구로 위장하지 않음. SVG는 질감 없는 기하 투영 |

형상 경계는 GLB를 다시 읽어 계산하며 최대0.01mm의 **소프트웨어 허용 오차**를 검사한다. 기업 제작 허용 오차가 아니다. glTF의 m 단위를 mm로 변환하고 Y-up/정면 방향과 노드 변환을 적용한다. 원래 카메라 보정/실측 정확도·제작 공차를 인증하지 않는다. 부위는 겹치는 타원체 집합으로, watertight 외피 결합·시접/원단 방향·패턴 전개/BOM을 제공하지 않는다. `must_have`는 모두 `human_review_required`, `design_approved/manufacturing_verified/effect_measured=false`다.

## 출처·권리

[ABO 공식 등록](https://registry.opendata.aws/amazon-berkeley-objects/) · [공식 데이터 설명](https://amazon-berkeley-objects.s3.us-east-1.amazonaws.com/README.md) · [CC BY4.0](https://creativecommons.org/licenses/by/4.0/).

원본 이미지/모델 귀속: **Amazon.com**. 데이터셋 제작: Matthieu Guillaumin, Thomas Dideriksen, Kenan Deng, Himanshu Arora, Jasmine Collins, Jitendra Malik. 공식 등록의 2023년 CC BY-NC→CC BY 변경을 따른다. 정해진3종 B07JLZC571/B074VLST26/B07BMQXWX1만 사용한다. 출처 URL·원본 SHA-256·가상 목표 치수·변경 사항을 설정/입력/보고서·GLB extras와 화면에 남긴다. 공개 데모에는 이3종의 **크기 변환 파생본**과 검사 결과만 포함하며 전체 원본 메타데이터/강의자료/회사 자료는 포함하지 않는다. 공개 사용이 허용된 자료의 파생본에 한정한 게시다.

Three.js0.186.1은 MIT, `client/vendor/THREE-LICENSE.txt` 보존. GLTFLoader·OrbitControls를 esbuild0.25.11로 로컬 번들해 CDN 없이 표시한다. `npm ci --ignore-scripts && npm run build:viewer`로 번들 재생성한다. 사전학습 모델/가중치 다운로드·GPU 학습은 이번 작업에서 수행하지 않았다.

## 저장·비동기 실행·API

- `results/generation.sqlite3`, `results/digital-samples/<run_id>/`: Git 제외.
- 요청은 `source_id/source_checksum/seed/request_key` 정확한 필드만, 중복JSON키·잘못된 시드/해시·임의 URL/경로를 거부한다. 입력은 U20 등록 버전 또는 고정된 공개 참조 목록에서만 고른다.
- `queued→running→succeeded/failed`. 최대4개 활성 작업, 트랜잭션으로 같은 요청의 중복 생성/동시 작업을 막는다. 같은 요청 키의 다른 입력/코드는409. 서버 재시작 시 중단 작업은 실패로 명시하고 새 요청을 받는다. 자동 재시도/클라우드 lease를 구현한 상태는 아니다.
- 입력/seed/엔진 파일SHA를 접수 시 고정. 새 폴더에 산출물을 쓴 뒤 성공을 확정한다. 실패/중간 결과는 다운로드하지 못한다. 같은 출력 폴더를 덮어쓰지 않는다.
- GET `/api/generation/catalog`, GET `/api/generation/runs/{id}`, POST `/api/generation/runs`, GET `/api/generation/artifacts/{id}/{file}`.
- Host는 loopback만, POST는 같은 출처만 허용한다. 완료 실행의 허용된 파일만 내려주고 서버/브라우저가 크기·SHA-256을 검사한다. 원격Supabase DS 스키마·RLS·승인 API는 변경하지 않았다.

산출물: input.json, baseline/candidate.glb, 각각의 front/side.svg, report.json, comparison.md, artifacts.json. 입력/원본·생성코드 해시·시드·시간·치수 검사·미지원 조건을 추적한다. 결과 기하/GLB는 같은 입력/seed/코드에서 재현하며 wall-clock 시간은 실행마다 다르다. 생성 시간은 Python 처리 시간으로 브라우저 렌더 속도·사용자 수정 시간·비용/메모리 측정이 아니다.

## 검사·남은 조건

단위 검사는 6가족/12명세의 실제 mesh·치수/해시, 시드/버전 재현, 원본 보존·변환, 잘못된 GLB/외부 참조, 중복/동시 요청·충돌·중단·손상 파일 거부와 저장 데모 파일을 확인한다. 브라우저는 합성/ABO 실제GLB·회전/뷰·다운로드·새 U20 버전 연결·복원·모바일·Pages 모드·기존PAT를 확인한다.

사전학습2D 추론은 [AI 경로](AI_SAMPLING.md), 합성 U22 검토/승인 이력은 [검토 경로](SAMPLE_REVIEWS.md)에 추가했다. 자유로운 원화/조건 준수·독립 제품 품질/현업 검토, 실제 사용자/기업 승인, U23 제작 패턴/BOM과 U24 실제 효과는 후속이다. 이 데모의 치수 오차가 작다는 이유로 봉제 품질·원가 절감·기업 과제 완료를 판정하지 않는다.
