"""Create a run-specific Markdown analysis report from stored synthetic results."""
def decision_report(result):
    d=result['decisions'];inv=d['inventory'];config=result['config']
    def f(x):return 'N/A' if x is None else f'{x:.3f}'
    lines=['# 합성 수요 세그먼트·예측·재고 실험 보고서','',
        '> 개발 검증용 합성 자료입니다. 실제 기업 개선 실적이나 최종 제출 승인 문서가 아닙니다.','',
        '## 실행 근거','',f"- 데이터: {result['dataset_version']} / {config['skus']} SKU × {config['weeks']}주 / seed {config['seed']}",
        f"- 데이터 SHA-256: `{result['dataset_checksum']}`",f"- 예측 설정 SHA-256: `{result['config_hash']}`",f"- 확장 설정 SHA-256: `{d['settings_hash']}`",f"- 확장 코드 SHA-256: `{d['code_revision']}`",
        f"- 선택 절단점: {d['selection_cutoff']}주, 검증 원점 {config['validation_origins']}개, 보류 {config['horizon']}주. 선택에 보류 정답 미사용.",
        '- 기존 기업 분류·모델 미확보. Naive/계절 Naive 및 임시 세그먼트 규칙을 대체 비교 대상으로 사용.','',
        '## 세그먼트·배정','', '| SKU | 분류 | ADI | CV² | 연속 이력 | 선택 모델 | 규칙 모델 |', '|---|---|---:|---:|---:|---|---|']
    for a in d['assignments']:lines.append(f"| {a['sku']} | {a['segment']} | {f(a['adi'])} | {f(a['cv2'])} | {a['history_n']} | {a['selected']} | {a['rule_model']} |")
    lines+=['','기존 사분면 경계 1.32/0.49를 임시 기술통계로 사용. 모델 최적 배정 이론으로 간주하지 않음. 누락/반품 뒤 연속 이력만 사용. 원점별 분류·변경 횟수·세그먼트별 성능·후보 제외 사유는 원본 JSON 참조.','',
        '## 공통 보류 평가','', '| 모델/배정 | n | SKU | MAE | 편향 | MASE | MASE n |','|---|---:|---:|---:|---:|---:|---:|']
    for m in d['paired_metrics']:lines.append(f"| {m['model']} | {m['n']} | {m['skus']} | {f(m['mae'])} | {f(m['bias'])} | {f(m['mase'])} | {m['mase_n']} |")
    i=d['interval_summary'];lines+=['',f"경험 10–90% 구간: n={i['n']}, 포함률={f(i['coverage'])}, 평균 폭={f(i['mean_width'])}. 검증 잔차 소표본·모델 선택 중복 사용으로 독립 보정이나 포함률을 보장하지 않음.",'',
        '## 재고: 예측 × 정책','',f"공통 {inv['common_skus']} SKU, {inv['evaluation_weeks']}주. 매주 과거 실현치로 재예측. 같은 초기재고·초기 미입고 0·2주 리드타임·1주 검토·3주 보호기간. 단가 1,000 KRW. 수요 미충족은 lost sales.",
        '', '| 예측 | 정책 | 충족률 | 평균 보유재고액 | 평균 미입고액 | 합계 투자액 |','|---|---|---:|---:|---:|---:|']
    for s in inv['scenarios']:lines.append(f"| {s['role']} | {s['policy']} | {f(s['fill_rate'])} | {f(s['on_hand_krw'])} | {f(s['pipeline_krw'])} | {f(s['invested_krw'])} |")
    lines+=['','투자액은 기말 보유+미입고의 평가기간 평균이다. 발주 잔량은 평가 종료 뒤 입고될 물량도 포함. 금융·회계상 현금흐름/운전자본 산출과 구분한다. 초기 상태 영향이 큰 단기 예시이며 장기 재고 성과로 일반화하지 않는다.','']
    for q in inv['comparisons']:lines.append(f"- {q['policy']}: 전체 Naive−선택 차이 {f(q['raw_difference_krw'])}원. 양쪽 모두 SKU별 95% 충족률인 {q['qualified_skus']}개만 집계한 조건부 차이 {f(q['qualified_difference_krw'])}원. 목표 미달·0수요는 조건부 집계 제외; 성공 판정 없음.")
    lines+=['','## 한계와 다음 검증','',
        '- 실제 기존 배정·품절 보정 수요·다창고/단위·회사 정책 미확보.',
        '- 평활계수 고정, 세그먼트 규칙은 프로젝트 임시 예시. 검증 오차 버퍼의 기본 보호기간 표본 3개뿐.',
        '- 긴 평가기간·리드타임/초기재고/단가 민감도와 독립 구간 보정·기업 검증 필요.',
        '- 재현: README의 demo 명령과 저장된 결과 JSON/설정·코드 해시를 함께 보관.','']
    return '\n'.join(lines)
