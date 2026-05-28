from app.product.scheduler import ProductScheduler


def test_schedule_future_transcript_and_fire_with_clock_advance():
    scheduler = ProductScheduler()
    item = scheduler.schedule_from_transcript(
        "Remind me to send the deck in 5 seconds",
        {"task": "send deck"},
    )

    assert item is not None
    assert item["status"] == "pending"
    assert scheduler.queue()[0]["status"] == "pending"

    result = scheduler.advance_clock(6)

    assert result["fired_count"] == 1
    assert scheduler.queue()[0]["status"] == "fired"


def test_fire_due_uses_wall_clock_without_test_advance():
    scheduler = ProductScheduler()
    item = scheduler.schedule_from_transcript(
        "Remind me to check the oven in 0 seconds",
        {"task": "check oven"},
    )

    assert item is not None
    result = scheduler.fire_due()

    assert result["fired_count"] == 1
    assert scheduler.queue()[0]["status"] == "fired"


def test_non_future_transcript_does_not_schedule():
    scheduler = ProductScheduler()

    assert scheduler.schedule_from_transcript("That was a normal sentence.", None) is None
    assert scheduler.queue() == []


def test_reset_clears_queue_and_clock():
    scheduler = ProductScheduler()
    scheduler.schedule_from_transcript("This is due tomorrow", None)
    assert scheduler.queue()

    scheduler.reset()

    assert scheduler.queue() == []
