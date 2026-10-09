"""Real local L4 acceptance. Cloud only with --execute-cloud; no private data copy."""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src_auto.agent_service import AgentService
from src_auto.agent_provider import configured_model
from src_auto.agent_cloud_budget import DeepSeekAgentBudget
from src_auto.config import load_mapping
from src_auto.l4_lab import L4SyntheticLab
from tools.validate_local_application_cloud import SyntheticControl


def execution_finished(row):
    """Require every real validated observation, even for a manual handoff.

    The model may deliberately request human review after finding candidates.
    That is not an interrupted tool run; it also is not a confirmed vulnerability.
    Resource failures, partial coverage and unvalidated observations still fail.
    """
    covered = {item.get('reference') for item in row.get('observations', []) if item.get('validated') is True}
    if not {'object-001', 'object-002', 'entry'} <= covered:
        return False
    return row.get('state') == 'completed' or (
        row.get('state') == 'needs-human' and row.get('reason') == 'request_human_review')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-cloud', action='store_true')
    args = parser.parse_args()
    if args.execute_cloud:
        # Explicit CLI flag is this foreground test's consent; never persist it.
        os.environ['SRC_AUTO_REMOTE_AI_CONSENT'] = 'yes'
        os.environ['SRC_AUTO_DEEPSEEK_CONSENT'] = 'yes'
    root = ROOT / 'validation/l4-business' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    (root / 'config').mkdir(parents=True, exist_ok=False)
    # Only non-secret policy is copied. Configured cloud model/key and spend
    # ledger stay at the original project root, and no API key is re-saved.
    (root / 'config/policy.yaml').write_text(json.dumps(load_mapping(ROOT / 'config/policy.yaml')), encoding='utf-8')
    (root / 'config/models.yaml').write_text('{}', encoding='utf-8')
    lab = L4SyntheticLab(root)
    lab.start()
    control, contexts, usages = SyntheticControl(root), [], []
    class Metered:
        def __init__(self): self.model = configured_model(ROOT, 'deepseek', True, True); self.provider = self.model.provider
        def decide(self, context):
            rendered = json.dumps(context, ensure_ascii=False)
            if any(x in rendered for x in lab.secret_markers): raise RuntimeError('private_context_blocked')
            contexts.append(context)
            answer = self.model.decide(context)
            usages.append({k: answer[k] for k in ('input_tokens', 'output_tokens', 'usage_estimated')})
            return answer
    service = AgentService(root, control, model_factory=lambda *a: Metered())
    control.agent = service
    service.business.cloud_budget_factory = lambda _: DeepSeekAgentBudget.configured(ROOT)
    results = {}
    try:
        target, row = lab.provision()
        for mode in ('standard', 'agent') if args.execute_cloud else ('standard',):
            if mode == 'agent': service.set_enabled(True)
            now = datetime.now(timezone.utc)
            value = dict(id=row['id'], revision=row['revision'], confirmIsolation=True, controls=True, mode=mode,
                provider='deepseek' if mode == 'agent' else 'none', allowCloud=mode == 'agent',
                windowStart=(now-timedelta(seconds=30)).isoformat(), windowEnd=(now+timedelta(minutes=12)).isoformat())
            approval = service.business.preview(value, args.execute_cloud)
            key = service.business.start(dict(approvalId=approval['approvalId'], confirmStart=True), args.execute_cloud)['id']
            deadline = time.monotonic()+650
            while time.monotonic()<deadline:
                result = service.history.get(key)
                if result.get('reportId') and service.current_id != key: break
                time.sleep(.2)
            else: service.cancel_run(key); raise RuntimeError('acceptance_timeout')
            results[mode] = result
        assertions = {'standard_execution_finished': execution_finished(results['standard']),
            'standard_real_16_requests': results['standard']['requests'] == 16,
            'standard_no_model': results['standard']['modelCalls'] == 0,
            'positive_and_negative_controls': results['standard']['candidates'] == 3 and not results['standard']['observations'][1]['candidate'],
            'no_outside_routes': all(path.startswith('/l4/') for path, _ in lab.received),
            'reports_readable': all((root/x['reportId']).is_file() for x in results.values())}
        if args.execute_cloud:
            def evidence(result):
                keys = {'reference', 'action', 'expected', 'statuses', 'fingerprints', 'baselineValid', 'equivalent',
                        'unexpectedRoles', 'missingExpectedRoles', 'inconclusiveRoles', 'checks', 'controlsValid', 'candidateCount', 'validated'}
                return {x['reference']: {k:v for k,v in x.items() if k in keys} for x in result['observations']}
            assertions.update(agent_execution_finished=execution_finished(results['agent']), agent_real_model=len(usages)>0,
                agent_16_requests=results['agent']['requests']==16, same_evidence=evidence(results['agent'])==evidence(results['standard']),
                feedback_received=any(x['observations'] for x in contexts), usage_metered=results['agent']['modelCalls']==len(usages))
        persisted = json.dumps(results)+''.join((root/x['reportId']).read_text(encoding='utf-8') for x in results.values())
        persisted += (root / 'data/agent.sqlite3').read_bytes().decode('latin1') + (root / 'data/src_auto.sqlite3').read_bytes().decode('latin1')
        assertions['secrets_not_persisted_or_sent'] = all(x not in persisted+json.dumps(contexts) for x in lab.secret_markers)
        summary = dict(assertions=assertions, passed=sum(assertions.values()), total=len(assertions), cloudUsage=usages,
                       results=results, limits='仅本轮合成本地 HTTP；未执行脚本、未知业务、外部目标或提交；费用是配置估算非账单')
        (root/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
        print('L4 验收：{}/{}；{}'.format(summary['passed'], summary['total'], root/'summary.json'), flush=True)
        for mode, result in results.items():
            print('{}: state={} requests={} candidates={} calls={} tokens={} seconds={} estimatedCny={}'.format(mode,
                result['state'], result['requests'], result['candidates'], result['modelCalls'], result['tokens'], result['elapsedSeconds'], result.get('estimatedCostCny', 0)), flush=True)
        return 0 if all(assertions.values()) else 1
    finally: service.close(); lab.close()


if __name__ == '__main__': sys.exit(main())
