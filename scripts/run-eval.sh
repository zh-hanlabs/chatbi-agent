#!/usr/bin/env bash
# 自动评估脚本:调用 /api/evaluations 并输出汇总。
# 用法: ./scripts/run-eval.sh [base-url]   默认 http://localhost:8080
set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
REPORT=$(curl -sf "$BASE_URL/api/evaluations")

echo "$REPORT" | python -c "
import json, sys
report = json.load(sys.stdin)
print(f\"总体: {report['passed']}/{report['total']} ({report['accuracy']:.1%})\")
for category, stat in report['byCategory'].items():
    print(f\"  {category:<10} {stat['passed']}/{stat['total']} ({stat['accuracy']:.1%})\")
failures = report.get('failures', [])
if failures:
    print(f\"失败用例 {len(failures)} 条:\")
    for failure in failures:
        print(f\"  [#{failure['id']}] {failure['category']} {failure['question']}\")
        print(f\"        actual: {failure['actual'][:120]}\")
    sys.exit(1)
"
