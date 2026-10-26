# 공개 거래 자료의 수요예측·장기 재고 시나리오 검증

출처: Chen, D. (2012). Online Retail II. UCI. DOI 10.24432/C5CG6D. CC BY 4.0. https://archive.ics.uci.edu/dataset/502/online+retail+ii

영국 선물용품 소매업체의 공개 청구 수량입니다. 오로라월드 자료·잠재 수요·회사 재고 실적이 아닙니다. 고객 ID·고객별 정보는 가공 입력/출력에 포함하지 않습니다.

선택 절단점: 68주. 워밍업 4주 뒤 32주 평가. 모델 선택·SKU 선정·버퍼는 절단점 이전 자료로 고정합니다.

## 같은 SKU·주간 대상의 순차 예측 평가

| 방식 | n | SKU | MAE | 편향 | MASE |
|---|---:|---:|---:|---:|---:|
| naive | 3146 | 99 | 178.269 | -3.379 | 0.913 |
| seasonal_naive | 3146 | 99 | 244.628 | 91.574 | 1.258 |
| selected | 3146 | 99 | 182.500 | 10.573 | 0.919 |

## 재고 시나리오 — 수량 기준

같은 시나리오 내 네 예측×정책 셀은 공통 SKU·동일 판매 경로·초기 조건을 사용합니다. 평균 기말 재고와 미입고를 구분합니다. 조달원가·비용은 미확보이므로 기본 결과에 금액·절감액을 부여하지 않습니다. 서비스 목표 .95·리드타임·초기재고는 예시입니다.

| 시나리오 | 예측 | 버퍼 | SKU | 충족률 | 목표 충족 SKU | 최악 SKU 충족률 | 평균 보유수량 합 | 평균 미입고수량 합 |
|---|---|---|---:|---:|---:|---:|---:|---:|
| lead2_history | naive | no_buffer | 99 | 0.838 | 11 | 0.514 | 91613.219 | 42575.281 |
| lead2_history | naive | validation_buffer | 99 | 0.931 | 62 | 0.542 | 138834.562 | 47258.000 |
| lead2_history | selected | no_buffer | 99 | 0.794 | 10 | 0.474 | 72725.000 | 40537.219 |
| lead2_history | selected | validation_buffer | 99 | 0.898 | 45 | 0.542 | 112055.031 | 45779.469 |
| lead2_zero | naive | no_buffer | 99 | 0.835 | 11 | 0.506 | 88713.281 | 42758.688 |
| lead2_zero | naive | validation_buffer | 99 | 0.927 | 62 | 0.542 | 136597.750 | 47211.500 |
| lead2_zero | selected | no_buffer | 99 | 0.790 | 10 | 0.476 | 69527.812 | 41031.844 |
| lead2_zero | selected | validation_buffer | 99 | 0.895 | 45 | 0.542 | 109267.312 | 46134.062 |
| lead4_history | naive | no_buffer | 99 | 0.866 | 27 | 0.590 | 169197.562 | 99996.312 |
| lead4_history | naive | validation_buffer | 99 | 0.916 | 57 | 0.596 | 213944.250 | 105259.969 |
| lead4_history | selected | no_buffer | 99 | 0.808 | 19 | 0.582 | 125339.281 | 90324.000 |
| lead4_history | selected | validation_buffer | 99 | 0.884 | 43 | 0.596 | 162427.781 | 98284.500 |

## 한계와 재현

- UK invoices only; boundary partial weeks removed
- Year 2010-2011 takes precedence from 2010-12-01; within-sheet repeated invoice lines retained
- No recorded invoice after first recorded positive sale means zero recorded sales under transaction-log coverage assumption, not proven zero demand
- not_started means before first recorded sale, not a known product launch date
- Negative/cancelled quantities retained separately, not subtracted from gross sales or treated as physical inventory receipts
- Stockouts, supplier lead time, procurement costs and initial inventory unknown; sale price in GBP is not procurement cost
- Policy replay is conditional on exogenous recorded sales as scenario demand; no causal evaluation or lost-demand reconstruction
- Warmup excluded only from scoring; terminal pipeline remains outstanding; no liquidation value or company savings claim

- 가공 데이터 SHA-256: `fc6b7eafd4162cc7b3694ba8c5cb5516ea31342bfd66b20767430fc5ef253017`
- 평가 코드 SHA-256: `dc10030012ed5598018426bfad5e26fae524e7b24e6302a023d53e9fdfd65c96`
- result.json, forecast.csv, inventory.csv, decisions.csv를 같은 실행의 산출물로 보관합니다. CSV는 동일 결과 객체에서 내보냅니다.
