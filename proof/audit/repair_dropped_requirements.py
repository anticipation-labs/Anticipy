"""Restore questions an older serializer dropped, for one explicitly named job.

Dry run by default. Does not invent a requirement, answer, approval, or task.
Only repairs an idle consequential plan with existing model-declared questions
but no workflow requirements. An incompatible research hand is re-routed by the
production model router. Writes use the live record's concurrency precondition.
"""
import argparse
import json
import os
from pathlib import Path
from brain import backend
from brain.anticipy_core import _required_from_missing, _missing_fact_question, job_lane
from brain.workflow import from_params, put_in_params, merge, Consequence
from proof.audit.task_revision_live import GatewayModel

ROOT = Path(__file__).resolve().parents[2]


def prepare(job, *, model=None, base='https://api.anticipy.ai'):
    params = json.loads(job.get('params') or '{}')
    plan = from_params(params)
    required = _required_from_missing(params.get('missing'))
    if (not plan or not required or plan.required or plan.facts or params.get('corrections')
            or plan.act or plan.lease or plan.receipt
            or plan.owner_ref != job.get('owner_ref') or plan.version != job.get('workflow_version')
            or plan.consequence != Consequence.CONSEQUENTIAL
            or job.get('status') not in ('awaiting_confirm', 'needs_user')):
        raise ValueError('This record does not have the dropped-question defect')
    revised = merge(plan, expected_version=plan.version, required=required)
    fields = revised.job_fields()
    fields.pop('workflow_id', None)
    fields['result'] = _missing_fact_question(revised.missing, fallback=list(revised.missing))
    if job.get('lane') == 'research' and params.get('_effect', {}).get('touches') == 'world':
        if model is None:
            raise ValueError('An incompatible executor requires a contextual routing verdict')
        fields['lane'] = job_lane(job['goal'], params, owner_ref=job['owner_ref'],
                                  backend_url=base, llm=model)
        if fields['lane'] == 'research':
            raise ValueError('The selected executor still cannot perform the declared effect')
    fields['params'] = json.dumps(put_in_params(params, revised))
    return fields


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    private = json.loads((ROOT / 'work/audit/secrets.json').read_text())
    os.environ['ANTICIPY_SERVICE_TOKEN'] = private['ANTICIPY_SERVICE_TOKEN']
    path = 'https://api.anticipy.ai/api/collections/jobs/records/' + args.job
    response = backend.get(path)
    response.raise_for_status()
    job = response.json()
    assert job.get('owner_ref') == args.owner and job.get('id') == args.job
    fields = prepare(job, model=GatewayModel())
    summary = {'job': args.job, 'previous_version': job['workflow_version'],
        'next_version': fields['workflow_version'], 'status': fields['status'],
        'question': fields['result'], 'lane': fields.get('lane', job.get('lane')),
        'approval_cleared': not fields['approval'], 'applied': False}
    if args.apply:
        assert response.headers.get('ETag'), 'No concurrency precondition'
        updated = backend.patch(path, json=fields, headers={'If-Match': response.headers['ETag']})
        updated.raise_for_status()
        actual = backend.get(path)
        actual.raise_for_status()
        assert all(actual.json().get(k) == v for k, v in fields.items())
        summary['applied'] = True
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
