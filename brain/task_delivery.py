"""Task questions use the same durable message/receipt path as chat replies."""
import hashlib
import json


def context(job):
    return {'purpose': 'task_question', 'job_id': job['id'],
            'version': job.get('workflow_version', 0), 'status': job['status'],
            'question': job.get('result') or ''}


def identity(job):
    # Exact persisted record identity, not semantic deduplication.
    return hashlib.sha256(json.dumps(context(job), sort_keys=True,
                                    ensure_ascii=False).encode()).hexdigest()


class TaskDelivery:
    def __init__(self, delivery):
        self.delivery = delivery

    def defer(self, job, reason):
        if job.get('owner_ref') != self.delivery.owner:
            return
        key = f'task-text:{identity(job)}:{reason}'
        if self.delivery.rows(f'external_event_id={json.dumps(key)}', 1):
            return
        try:
            self.delivery.create(kind='notification_status', goal=job['id'],
                text=json.dumps(context(job)), decision=reason, external_event_id=key)
        except Exception:
            pass  # No external effect; the next sweep can record this again.

    def count(self, job):
        count = 0
        for row in self.delivery.rows('kind="reply_outbox"', 200):
            try:
                meta = json.loads(row.get('text') or '{}')
                if meta.get('purpose') == 'task_question' and meta.get('job_id') == job['id']:
                    count += 1
            except (ValueError, TypeError):
                continue
        return count

    def publish(self, job, text):
        return self.delivery.publish(
            {'id': f'task-question:{identity(job)}', 'owner_ref': job.get('owner_ref'),
             'source': 'task_question'}, text, metadata=context(job))
