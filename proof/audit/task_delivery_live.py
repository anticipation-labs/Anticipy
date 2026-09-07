"""Production database proof using one disposable account with no phone.

Exercises real owner-scoped storage and the production delivery adapter from
this checkout. The provider must never be called. This is not a carrier test.
"""
import json
import os
import secrets
from urllib.parse import urlencode
from pathlib import Path
from proof.audit.live_api_release import request
from brain.reply_delivery import ReplyDelivery
from brain.task_delivery import TaskDelivery, context
from brain import backend
from brain.workflow import new_plan, put_in_params, cancel, approve, claim, needs_user, Consequence

BASE = 'https://api.anticipy.ai'
ROOT = Path(__file__).resolve().parents[2]


def main():
    private = json.loads((ROOT / 'work/audit/secrets.json').read_text())
    os.environ['ANTICIPY_SERVICE_TOKEN'] = private['ANTICIPY_SERVICE_TOKEN']
    email = 'task-delivery-' + secrets.token_hex(10) + '@anticipy-test.invalid'
    password = secrets.token_urlsafe(30)
    status, owner, _ = request(BASE, 'POST', '/api/collections/owners/records',
        {'email': email, 'password': password, 'passwordConfirm': password})
    assert status == 200 and owner.get('id')
    status, auth, _ = request(BASE, 'POST', '/api/collections/owners/auth-with-password',
        {'identity': email, 'password': password})
    assert status == 200 and auth.get('token')
    token = auth['token']
    checks = []

    class NoProvider:
        def send(self, *args, **kwargs):
            raise AssertionError('The synthetic fixture must never send a text')

    try:
        question = 'Which export format should the manufacturer receive?'
        plan = new_plan(owner_ref=owner['id'], lineage_key='isolated-question-proof',
            goal='Synthetic manufacturing question', consequence=Consequence.CONSEQUENTIAL,
            required=[question], source_event_id='synthetic')
        payload = dict(plan.job_fields(), owner_ref=owner['id'], result=question,
            goal=plan.goal, lane='', device_id='release-proof',
            params=json.dumps(put_in_params({'missing': [question]}, plan)))
        status, job, _ = request(BASE, 'POST', '/api/collections/jobs/records', payload, token)
        assert status == 200 and job.get('id')
        delivery = ReplyDelivery(BASE, owner['id'], NoProvider(), lambda: None)
        adapter = TaskDelivery(delivery)
        adapter.defer(job, 'text_daily_limit')
        adapter.defer(job, 'text_daily_limit')
        rows = delivery.rows('kind="notification_status"', 50)
        assert len(rows) == 1 and json.loads(rows[0]['text']) == context(job)
        checks.append('Exact task pause stored once in live database')
        first = adapter.publish(job, 'Which export format should the manufacturer receive?')
        adapter.publish(job, 'A duplicate cannot change the already saved text')
        outboxes = delivery.rows('kind="reply_outbox"', 50)
        assert len(outboxes) == 1 and outboxes[0]['decision'] == 'reply_pending'
        assert json.loads(outboxes[0]['text']) == context(job)
        checks.append('Question saved once with matching durable outbox and no phone send')
        query = urlencode({'perPage': 200, 'filter': 'kind="reply_outbox" && owner_ref=' + json.dumps(owner['id'])})
        status, page, _ = request(BASE, 'GET', '/api/collections/events/records?' + query, token=token)
        assert status == 200 and any(x['id'] == outboxes[0]['id'] for x in page['items'])
        checks.append('Signed-in phone can read its task receipt metadata')
        path = '/api/collections/jobs/records/' + job['id']
        status, _, task_headers = request(BASE, 'GET', path, token=token)
        assert status == 200
        cancelled = cancel(plan, reason='Isolated proof completed')
        cancellation = dict(cancelled.job_fields(), params=json.dumps(put_in_params({}, cancelled)))
        cancellation.pop('workflow_id', None)
        status, changed, _ = request(BASE, 'PATCH', path, cancellation, token,
            {'If-Match': task_headers['ETag']})
        assert status == 200, (status, changed)
        delivery.deliver(outboxes[0])
        current = delivery.rows('kind="reply_outbox"', 50)
        assert current[0]['decision'] == 'question_superseded'
        checks.append('Cancelled question suppressed by fresh live task read')
        # Reproduce the old serializer's inconsistent task, then traverse real
        # server states. This owner is excluded from the fleet and has no hand.
        legacy = new_plan(owner_ref=owner['id'], lineage_key='isolated-replan-proof',
            goal='Synthetic external action', consequence=Consequence.CONSEQUENTIAL,
            source_event_id='synthetic-replan')
        old_params = {'missing': [question], '_effect': {'touches': 'world'}}
        created = backend.post(BASE + '/api/collections/jobs/records', json=dict(
            legacy.job_fields(), owner_ref=owner['id'], goal=legacy.goal, lane='research',
            result=question, params=json.dumps(put_in_params(old_params, legacy))))
        created.raise_for_status()
        legacy_path = BASE + '/api/collections/jobs/records/' + created.json()['id']
        def transition(p, headers=None):
            fields = dict(p.job_fields(), params=json.dumps(put_in_params(old_params, p)))
            fields.pop('workflow_id', None)
            if p.lease:
                fields['claimed_by'] = p.lease.actor_id
            response = backend.patch(legacy_path, json=fields, headers=headers or {})
            assert response.ok, (response.status_code, response.text[:300])
        authorized = approve(legacy, expected_version=legacy.version, owner_words='Synthetic approval')
        transition(authorized)
        running = claim(authorized, expected_version=authorized.version, actor_id='worker-proof', token='proof-lease')
        transition(running)
        parked = needs_user(running, lease_token='proof-lease', reason='Synthetic read-only hand refusal')
        transition(parked, {'X-Anticipy-Lease': 'proof-lease'})
        from proof.audit.repair_dropped_requirements import prepare
        from proof.audit.task_revision_live import GatewayModel
        current = backend.get(legacy_path)
        current.raise_for_status()
        repaired = prepare(current.json(), model=GatewayModel())
        changed = backend.patch(legacy_path, json=repaired, headers={'If-Match': current.headers['ETag']})
        assert changed.ok, (changed.status_code, changed.text[:300])
        actual = backend.get(legacy_path).json()
        assert actual['workflow_state'] == 'draft' and actual['lane'] == '' and not actual['approval']
        assert json.loads(actual['params'])['_workflow']['required'] == [question]
        checks.append('Old blocked research task safely re-held with required question and no approval')
        stale = backend.patch(legacy_path, json=repaired, headers={'If-Match': current.headers['ETag']})
        assert stale.status_code == 412
        checks.append('Concurrent or repeated repair refused by live version precondition')
    finally:
        status, removed, _ = request(BASE, 'POST', '/me/delete', {'confirm': 'delete'}, token)
        assert status == 200 and removed.get('account_deleted') is True
        checks.append('Disposable account and records removed')
    result = {'scope': __doc__, 'checks': checks, 'provider_calls': 0}
    (ROOT / 'research/overnight-2026-09-07/task-delivery-live-evidence.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
