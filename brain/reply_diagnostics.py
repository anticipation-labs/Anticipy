"""Closed, content-free failure facts for reply interpretation and delivery.

These are observations, never a retry license or an owner instruction. No
exception text, model output, request URL, provider body or credential belongs
in this module's output.
"""
from __future__ import annotations

import json
import re

import httpx
import requests

from . import backend
from .llm import CallCeilingExceeded, DeadlineExceeded


STAGES = frozenset({'reply_classification', 'sms_send'})
CATEGORIES = frozenset({
    'no_live_model', 'budget_deadline', 'budget_calls',
    'malformed_json', 'invalid_intent', 'timeout', 'connection_error',
    'provider_auth_error', 'provider_payment_error', 'provider_rate_limit',
    'provider_server_error', 'provider_http_error',
    'provider_response_invalid_json', 'provider_response_invalid_shape',
    'provider_response_missing_handle', 'provider_response_rejected',
    'provider_response_error', 'unexpected_error',
})
MODEL_ROLES = frozenset({'strong', 'main', 'none'})


def diagnostic(stage, category, http_status=None, *, model_role=None) -> dict:
    """Serialize only exact primitive values from the approved vocabulary."""
    if type(stage) is not str or stage not in STAGES:
        raise ValueError('Unsupported diagnostic stage')
    safe_category = (category if type(category) is str and category in CATEGORIES
                     else 'unexpected_error')
    out = {'version': 1, 'stage': stage, 'category': safe_category}
    if type(http_status) is int and 100 <= http_status <= 599:
        out['http_status'] = http_status
    if type(model_role) is str and model_role in MODEL_ROLES:
        out['model_role'] = model_role
    return out


def exception_diagnostic(error, stage='sms_send') -> dict:
    """Use known exception types and numeric status, never their messages."""
    status = None
    category = 'unexpected_error'
    try:
        if isinstance(error, DeadlineExceeded):
            category = 'budget_deadline'
        elif isinstance(error, CallCeilingExceeded):
            category = 'budget_calls'
        elif isinstance(error, (httpx.HTTPStatusError, requests.HTTPError)):
            status = getattr(getattr(error, 'response', None), 'status_code', None)
            category = 'provider_http_error'
            if type(status) is int:
                if status in (401, 403):
                    category = 'provider_auth_error'
                elif status == 402:
                    category = 'provider_payment_error'
                elif status == 429:
                    category = 'provider_rate_limit'
                elif 500 <= status <= 599:
                    category = 'provider_server_error'
        elif isinstance(error, (httpx.TimeoutException, requests.Timeout, TimeoutError)):
            category = 'timeout'
        elif isinstance(error, (httpx.TransportError, requests.ConnectionError,
                                ConnectionError, OSError)):
            category = 'connection_error'
        elif isinstance(error, json.JSONDecodeError):
            category = 'provider_response_invalid_json'
    except Exception:
        # Even malformed exception objects cannot make diagnostics a new
        # reason to lose a reply. Do not render the exception while handling it.
        status, category = None, 'unexpected_error'
    return diagnostic(stage, category, status)


def reply_parse_failure(text) -> str:
    """Classify failure using the existing parser's framing, without repair.

    The caller already rejected the answer. Repeat its exact greedy object
    framing only to distinguish malformed JSON from an invalid intent. This
    function neither returns model content nor changes parser acceptance.
    """
    if not isinstance(text, str):
        return 'malformed_json'
    match = re.search(r'\{[\s\S]*\}', text)
    if match is None:
        return 'malformed_json'
    try:
        json.loads(match.group(0))
    except (ValueError, TypeError):
        return 'malformed_json'
    return 'invalid_intent'


def record_reply_diagnostic(base, owner_ref, event, metadata) -> bool:
    """One best-effort, exact-input diagnostic write; never alter the input.

    timeout=2 bounds requests' connect/read inactivity, not a hard wall-clock
    deadline. It is independent of the spent model budget. No diagnostic read,
    retry or provider operation follows either success or failure.
    """
    try:
        if (type(owner_ref) is not str or not owner_ref.strip()
                or type(base) is not str or not base
                or type(event) is not dict or event.get('owner_ref') != owner_ref
                or type(event.get('id')) is not str or not event['id'].strip()
                or type(metadata) is not dict
                or metadata.get('stage') != 'reply_classification'):
            return False
        if not (event.get('kind') in ('app_reply', 'sms_reply') or
                (event.get('kind') == 'transcript' and event.get('source') == 'typed')):
            return False
        safe = diagnostic('reply_classification', metadata.get('category'),
                          metadata.get('http_status'), model_role=metadata.get('model_role'))
        response = backend.post(f'{base.rstrip("/")}/api/collections/events/records', json={
            'kind': 'notification_status', 'decision': 'reply_diagnostic',
            'source': 'reply_classifier', 'device_id': 'anticipy-brain',
            'owner_ref': owner_ref, 'goal': event['id'],
            'external_event_id': f'reply-diagnostic:{event["id"]}',
            'text': json.dumps(safe, separators=(',', ':')),
        }, timeout=2)
        response.raise_for_status()
        return True
    except Exception:
        return False
