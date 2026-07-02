"""Smoke tests for the proactive contract layer."""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass

from anticipy_engine.proactive.contracts import (
    RAW_AUDIO_FIELD_NAMES,
    Confidence,
    Decision,
    DecisionKind,
    EngineStatusEvent,
    GatewayActionPlan,
    GatewayBrowserRun,
    GatewayChannelMirror,
    GatewayMemoryMutation,
    GatewayProof,
    Intent,
    NotificationChannel,
    ProactiveGatewayEnvelope,
    Reversibility,
    TranscriptChunk,
    Urgency,
)


CONTRACT_TYPES = [
    TranscriptChunk,
    Confidence,
    Urgency,
    Intent,
    Decision,
    EngineStatusEvent,
]


def test_contracts_do_not_carry_raw_audio() -> None:
    for typ in CONTRACT_TYPES:
        assert is_dataclass(typ), typ
        field_names = {f.name for f in fields(typ)}
        forbidden = field_names & RAW_AUDIO_FIELD_NAMES
        assert not forbidden, f"{typ.__name__} has raw-audio fields: {sorted(forbidden)}"


def test_transcript_decision_wire_payload_is_json_safe() -> None:
    chunk = TranscriptChunk(
        user_id="owner",
        session_id="session-1",
        sequence=1,
        text="Marcus asked me to send the deck before Friday.",
        source="browser_mic",
        source_anchors=["ST-LISTEN-REAL-LIFE"],
    )
    intent = Intent(
        user_id=chunk.user_id,
        text="Send Marcus the deck before Friday.",
        action_verb="send",
        evidence_chunk_ids=[chunk.chunk_id],
        source_anchors=["ST-ACT-ASK-SILENT", "ST-MONEY-CONFIRM"],
    )
    decision = Decision(
        intent=intent,
        kind=DecisionKind.ASK,
        confidence=Confidence(0.91, "Clear commitment, but sending needs approval."),
        reversibility=Reversibility.IRREVERSIBLE,
        urgency=Urgency(4, "Due before Friday."),
        reason="Sending a message needs owner approval.",
        user_facing_question="I drafted the email to Marcus. Okay to send?",
        proof_scope="Proves a draft exists; does not prove it was sent.",
    )
    payload = {
        "chunk": chunk.to_wire(),
        "decision": decision.to_wire(),
        "status": EngineStatusEvent(
            decision_id=decision.decision_id,
            stage="waiting",
            message="Waiting for your yes.",
        ).to_wire(),
    }

    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["chunk"]["text"] == chunk.text
    assert decoded["decision"]["kind"] == "ask"
    assert decoded["decision"]["reversibility"] == "irreversible"
    assert decoded["decision"]["urgency"]["level"] == 4
    assert Urgency(4).channel == NotificationChannel.SMS


def test_proactive_gateway_envelope_is_json_safe() -> None:
    envelope = ProactiveGatewayEnvelope(
        event_id="gw-test",
        user_id="owner",
        source="app",
        source_label="phase_zero_text",
        raw_input_ref={"text_preview": "Remind me to call Maya tomorrow."},
        structured_summary="One reminder was understood.",
        facts=[{"text": "Maya matters."}],
        open_loops=[{"text": "Call Maya tomorrow."}],
        possible_tasks=[{"title": "Call Maya", "status": "needs_approval"}],
        suggested_actions=[
            GatewayActionPlan(
                route="memory",
                action="write_memory",
                title="Call Maya",
                approval_required=False,
                card_id="card-1",
            )
        ],
        memory_mutations=[
            GatewayMemoryMutation(
                drawer="open_loops",
                operation="written",
                text="Call Maya tomorrow.",
                memory_id="mem-1",
            )
        ],
        approval_required=True,
        channel_mirrors=[
            GatewayChannelMirror(channel="app", status="available"),
            GatewayChannelMirror(channel="text", status="queued"),
        ],
        browser_run=GatewayBrowserRun(task="Look up return policy", success=True, answer="Found it."),
        proof=[GatewayProof(type="memory_read_back", scope="memory", summary="Memory came back.")],
        follow_up_at=123.0,
        source_of_truth_tags=["ST-ACTIVE-LISTENING", "ST-NO-FAKE-DONE"],
        confidence=0.92,
        status="needs_approval",
    )

    decoded = json.loads(json.dumps(envelope.to_wire()))

    assert decoded["event_id"] == "gw-test"
    assert decoded["source"] == "app"
    assert decoded["suggested_actions"][0]["action"] == "write_memory"
    assert decoded["memory_mutations"][0]["drawer"] == "open_loops"
    assert decoded["channel_mirrors"][1]["channel"] == "text"
    assert decoded["browser_run"]["answer"] == "Found it."
    assert decoded["status"] == "needs_approval"


if __name__ == "__main__":
    test_contracts_do_not_carry_raw_audio()
    test_transcript_decision_wire_payload_is_json_safe()
    test_proactive_gateway_envelope_is_json_safe()
    print("proactive contracts: ok")
