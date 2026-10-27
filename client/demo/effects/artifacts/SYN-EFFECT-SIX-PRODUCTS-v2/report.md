# 디지털 샘플링 효과 측정 · 합성 보고

합성 짝 비교의 기술통계입니다. 실제 기업 효과·인과 효과·BOM 정확도/오류율·비용 절감은 미측정입니다.

이 보고서는 저장 시점의 불변 스냅샷이다. 현재 승인/연결의 유효성은 앱에서 다시 조회한다.

연구 SYN-EFFECT-SIX-PRODUCTS / 버전 2 / 기록 2026-10-27T07:20:30.499153+00:00

## 측정 정의

명세 접수→샘플 최종 검토 완료의 달력 경과시간(대기 포함). 제작 개수와 사건 횟수를 분리한다. BOM 정상 설계 변경·미분류는 오류 수정과 분리한다.

## 지표별 동일 짝 비교

| 지표 | 비교 제품 수 / 전체 | 현행 합계 | 시범 합계 | 감소량 | 감소율 |
|---|---|---|---|---|---|
| 실물 제작 수량 (개) | 2 / 6 | 6 | 5 | 1 | 16.667% |
| 실물 제작 사건 (회) | 2 / 6 | 4 | 3 | 1 | 25.000% |
| 개발 달력 경과시간 (시간) | 2 / 6 | 672.000 | 624.000 | 48.000 | 7.143% |
| BOM 오류 수정 사건 (건) | 2 / 6 | 2 | 2 | 0 | 0.000% |

감소량=현행−시범. 음수는 악화다. 현행 합계0이면 비율은 계산하지 않는다. 관측 없는 값은0으로 채우지 않는다. 지표마다 제외된 제품이 달라질 수 있으며 개별 감소율의 단순 평균을 쓰지 않는다.

## 제품별 관측·제외 근거

### SYN-BUNNY

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 complete.
BOM 정상 변경 현행 1 / 시범 1; 미분류 현행 0 / 시범 0.

- 실물 제작 수량: 비교 가능
- 실물 제작 사건: 비교 가능
- 개발 달력 경과시간: 비교 가능
- BOM 오류 수정 사건: 비교 가능
### SYN-COW

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 complete.
BOM 정상 변경 현행 1 / 시범 1; 미분류 현행 0 / 시범 0.

- 실물 제작 수량: 비교 가능
- 실물 제작 사건: 비교 가능
- 개발 달력 경과시간: 비교 가능
- BOM 오류 수정 사건: 비교 가능
### SYN-DOG

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 complete.
BOM 정상 변경 현행 미측정/비교 불가 / 시범 0; 미분류 현행 미측정/비교 불가 / 시범 0.

- 실물 제작 수량: 제외 · workflow_anchor_missing, baseline_unmeasured, physical_coverage_incomplete
- 실물 제작 사건: 제외 · workflow_anchor_missing, baseline_unmeasured, physical_coverage_incomplete
- 개발 달력 경과시간: 제외 · workflow_anchor_missing, baseline_unmeasured
- BOM 오류 수정 사건: 제외 · workflow_anchor_missing, baseline_unmeasured, bom_coverage_incomplete
### SYN-CAT

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 complete.
BOM 정상 변경 현행 1 / 시범 0; 미분류 현행 0 / 시범 1.

- 실물 제작 수량: 제외 · workflow_anchor_missing
- 실물 제작 사건: 제외 · workflow_anchor_missing
- 개발 달력 경과시간: 제외 · workflow_anchor_missing
- BOM 오류 수정 사건: 제외 · workflow_anchor_missing, bom_coverage_incomplete, bom_reason_unknown
### SYN-CACTUS

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 in_progress.
BOM 정상 변경 현행 1 / 시범 1; 미분류 현행 0 / 시범 0.

- 실물 제작 수량: 제외 · workflow_anchor_missing, pilot_in_progress, definition_mismatch, physical_coverage_incomplete
- 실물 제작 사건: 제외 · workflow_anchor_missing, pilot_in_progress, definition_mismatch, physical_coverage_incomplete
- 개발 달력 경과시간: 제외 · workflow_anchor_missing, pilot_in_progress, definition_mismatch
- BOM 오류 수정 사건: 제외 · workflow_anchor_missing, pilot_in_progress, definition_mismatch, bom_coverage_incomplete
### SYN-FRUIT

현행 2026-09-01~2026-09-30 / 시범 2026-10-01~2026-10-25; 시범 상태 unmeasured.
BOM 정상 변경 현행 미측정/비교 불가 / 시범 미측정/비교 불가; 미분류 현행 미측정/비교 불가 / 시범 미측정/비교 불가.

- 실물 제작 수량: 제외 · workflow_anchor_missing, baseline_unmeasured, pilot_unmeasured, physical_coverage_incomplete
- 실물 제작 사건: 제외 · workflow_anchor_missing, baseline_unmeasured, pilot_unmeasured, physical_coverage_incomplete
- 개발 달력 경과시간: 제외 · workflow_anchor_missing, baseline_unmeasured, pilot_unmeasured
- BOM 오류 수정 사건: 제외 · workflow_anchor_missing, baseline_unmeasured, pilot_unmeasured, bom_coverage_incomplete

## 가정·한계·운영

U20의 가상 현행을 재사용하고 시범 제작/BOM 사건을 새로 합성했다. 같은 제품 범위/난이도·정의라는 가정이며 실제 현장 비교군이 아니다. U22/U23 해시는 디지털 이력 참조이고 합성 제작 사건이 실제로 일어났다는 증거가 아니다. 기업 실측·인과 개선·실제 비용/정확도는 미측정이다.

제품 난이도·업무량·관측창·완결성·동일 정의의 현업 확인이 필요하다. 통계적 유의성·인과 개선·기업 목표 달성은 판정하지 않는다. 실제 작업/대기시간 분리·BOM 전체 오류 기회·비용은 미확보다. U22/U23의 디지털 승인은 실물 제작의 검증이 아니다.

입력 수정 시 새 버전과 부모 SHA·사유를 등록한다. 승인 철회/명세/패턴 변경 후 현재 재계산을 확인하고 필요하면 새 보고서를 저장한다. 원본 입력·products.csv·events.csv·lineage.json·manifest의 해시로 추적한다. 실제 사용자 인증·기업 입력·Supabase DS 저장은 후속이다.

## 재현·제출 연결

기본 Python 서버의 동일 검증/계산부를 사용한다. `tools/build_effect_demo.py`로 자체 합성 저장 예제를 새 출력 경로에 재현한다. DS-05 지표/분모/제외 근거와 DS-06 효과/운영 보고 초안이다. 실제 기업 중간/최종 인수 보고서로 간주하지 않는다.

입력 SHA: 16303379388fc2c7bb80e9d2f0e3cf4f43423c08d0ae91c800bab076096edf00
출처 SHA: 696f8a3a32ed1103c01ee44e7e73d880d045bc582edb704cba0e9cd91439d769
엔진 SHA: e08c7fa2f218d33a0c90de95508c3c1404f49884e27ccebeb454a9b8b519d2ef