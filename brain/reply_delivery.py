"""One durable reply, independently delivered to the feed and to text.

The event id is the deduplication key. Message wording never selects a route.
The unique attempt record is claimed before contacting the provider; a lost
provider response remains unconfirmed instead of authorizing a duplicate.
"""
from __future__ import annotations

import json
from . import backend


class ReplyDelivery:
    def __init__(self, base, owner_ref, transport, phone):
        self.base = base.rstrip('/')
        self.owner = owner_ref
        self.transport = transport
        self.phone = phone  # Re-read the canonical profile at delivery time.

    @property
    def url(self):
        return f'{self.base}/api/collections/events/records'

    def rows(self, expression, limit=100):
        response = backend.get(self.url, params={
            'filter': f'owner_ref={json.dumps(self.owner)} && ({expression})',
            'sort': 'created', 'perPage': limit,
        })
        response.raise_for_status()
        return response.json().get('items', [])

    def create(self, **body):
        response = backend.post(self.url, json={
            'device_id': 'anticipy-brain', 'owner_ref': self.owner, **body,
        })
        response.raise_for_status()
        return response.json()

    def publish(self, event, body, media=None):
        if not self.owner or event.get('owner_ref') != self.owner or not event.get('id'):
            raise ValueError('A reply requires its canonical owner and input event')
        key = f'reply:{event["id"]}'
        found = self.rows(f'external_event_id={json.dumps(key)}', 1)
        if found:
            row = found[0]
        else:
            try:
                row = self.create(kind='anticipy_text', text=body,
                    decision='', goal=event['id'],
                    source=event.get('source') or '', external_event_id=key)
            except Exception:
                # A concurrent winner or a lost create response may have saved
                # it. Never send until that exact reply can be read back.
                found = self.rows(f'external_event_id={json.dumps(key)}', 1)
                if not found:
                    raise
                row = found[0]
        key = f'reply-outbox:{row["id"]}'
        pending = self.rows(f'external_event_id={json.dumps(key)}', 1)
        if not pending:
            try:
                pending = [self.create(kind='reply_outbox', text='', goal=row['id'],
                    decision='reply_pending', external_event_id=key)]
            except Exception:
                pending = self.rows(f'external_event_id={json.dumps(key)}', 1)
                if not pending:
                    raise
        try:
            self.deliver(pending[0], media=media)
        except Exception:
            # The durable queue is the retry, so an unavailable phone/profile
            # read cannot turn successfully saved reasoning into an apology.
            pass
        return {'via': 'durable-reply', 'body': row['text'], 'id': row['id']}

    def finish(self, row, state):
        response = backend.patch(f'{self.url}/{row["id"]}',
                                 json={'decision': state})
        response.raise_for_status()

    def deliver(self, row, media=None):
        from .conversation import MockTransport
        if isinstance(self.transport, MockTransport):
            return  # No provider attempt exists to fence; keep the reply queued.
        if row.get('owner_ref') != self.owner or row.get('decision') != 'reply_pending':
            return
        messages = self.rows(f'id={json.dumps(row["goal"])} && kind="anticipy_text"', 1)
        if not messages:
            self.finish(row, 'reply_missing')
            return
        message = messages[0]
        phone = self.phone()
        if not phone:
            # Keep pending: saving a verified number later can deliver the same
            # answer without running its reasoning or task effects again.
            return
        allowed = getattr(self.transport, 'before_send', None)
        if allowed is not None and not allowed(phone):
            return  # A known authorization refusal is not a provider attempt.
        key = f'reply-sms:{message["id"]}'
        attempts = self.rows(f'external_event_id={json.dumps(key)}', 1)
        if attempts:
            self.finish(row, attempts[0].get('decision') or 'sms_unconfirmed')
            return
        try:
            attempt = self.create(kind='notification_status',
                text='Text delivery started; provider acceptance is not yet known.',
                goal=message['id'], decision='sms_unconfirmed', external_event_id=key)
        except Exception:
            # Only an unambiguous create winner is allowed to contact SendBlue.
            return
        state = 'sms_unconfirmed'
        result = None
        try:
            result = (self.transport.send(phone, message['text'], media=media)
                      if media else self.transport.send(phone, message['text']))
            if result and not result.get('mock') and not result.get('skipped'):
                state = 'sms_delivered' if result.get('delivered') else 'sms_accepted'
            elif not result or result.get('skipped'):
                state = 'sms_skipped'
            else:
                state = 'sms_mock'
        except Exception:
            # Do not infer rejection from an exception string: the request may
            # have reached the provider. This is explicitly not "delivered".
            pass
        try:
            response = backend.patch(f'{self.url}/{attempt["id"]}', json={
                'decision': state,
                'text': json.dumps({'state': state, 'provider_id':
                                   (result or {}).get('sid', '')}),
            })
            response.raise_for_status()
            self.finish(row, state)
        except Exception:
            # The original attempt fence survives response loss or restart.
            pass

    def sweep(self):
        for row in self.rows('kind="reply_outbox" && decision="reply_pending"'):
            try:
                self.deliver(row)
            except Exception:
                # One malformed/orphaned reply cannot stop later answers.
                continue
