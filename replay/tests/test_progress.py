import pytest


def row(round_number, value, label="low_defense"):
    return {"round": round_number, "habits": {label: {"mastery": value}}}


@pytest.mark.parametrize("values,phrase", [
    ([0.2, 0.3, 0.5], "rose"),
    ([0.5, 0.3, 0.2], "fell"),
    ([0.2, 0.2, 0.2], "stayed about the same"),
    ([0.2, 0.6, 0.4], "went up and down"),
])
def test_estimates_are_interpreted_not_read_out(values, phrase):
    from replay.progress import estimate_progress

    facts = estimate_progress([row(i, value) for i, value in enumerate(values, 1)])
    text = facts[0]["text"]
    assert phrase in text
    assert "blocking lows" in text
    assert "round 1" in text and "round 3" in text
    assert "Analytics reports" not in text and "low_defense" not in text
    assert "do not confirm improvement" in text
    assert facts[0]["citations"] == []


def test_single_snapshot_cannot_establish_a_round_comparison():
    from replay.progress import estimate_progress

    text = estimate_progress([row(1, 0.285)])[0]["text"]
    assert "only one" in text.lower() and "cannot compare" in text.lower()
    assert "0.285" in text and "blocking lows" in text


def test_progress_prioritizes_plain_topics_over_internal_after_block_keys():
    from replay.progress import estimate_progress

    rows = [{"round": 1, "habits": {"after_block:any": {"mastery": 0.2},
             "low_defense": {"mastery": 0.3}, "throw_break": {"mastery": 0.4}}}]
    facts = estimate_progress(rows)
    assert "blocking lows" in facts[0]["text"]
    assert "breaking throws" in facts[1]["text"]
    assert all("after_block" not in fact["text"] for fact in facts)


def test_missing_latest_topic_does_not_reuse_an_older_estimate_as_current():
    from replay.progress import estimate_progress

    facts = estimate_progress([row(1, 0.2), row(2, 0.5), {"round": 3, "habits": {}}])
    assert "no current estimate" in facts[0]["text"].lower()
    assert "rose" not in facts[0]["text"]


def test_conflicting_same_round_estimates_are_not_compared():
    from replay.progress import estimate_progress

    with pytest.raises(ValueError):
        estimate_progress([row(1, 0.2), row(1, 0.7)])


def point(round_number, frame, action, situation="low_defense", correct=None):
    event = {"detail": {} if correct is None else {"correct": correct}}
    return {"round": round_number, "frame": frame, "situation": situation,
            "human_action": action, "evidence": [{"record": event}]}


def test_observed_low_blocking_is_compared_with_real_round_evidence():
    from replay.progress import observed_progress

    decisions = [point(1, 10, "hit"), point(1, 20, "blocked"),
                 point(2, 10, "blocked"), point(2, 20, "blocked")]
    fact, = observed_progress(decisions)
    assert "larger share" in fact["text"]
    assert "1 of 2 in round 1" in fact["text"] and "2 of 2 in round 2" in fact["text"]
    assert "not proof of lasting improvement" in fact["text"]
    assert fact["citations"] == [{"round": 1, "frame": 10}, {"round": 2, "frame": 20}]


def test_observed_mixed_rounds_are_not_cherry_picked_as_consistent_improvement():
    from replay.progress import observed_progress

    decisions = [point(1, 1, "hit"), point(2, 1, "blocked"), point(3, 1, "hit")]
    text = observed_progress(decisions)[0]["text"]
    assert "went up and down" in text
    assert "1 of 1 in round 2" in text


def test_a_single_observed_round_has_no_between_round_trend():
    from replay.progress import observed_progress

    assert observed_progress([point(1, 1, "blocked")]) == []


@pytest.mark.parametrize("actions,phrase", [
    (["blocked", "hit"], "smaller share"), (["blocked", "blocked"], "stayed the same"),
])
def test_observed_flat_and_declining_rates_are_explained(actions, phrase):
    from replay.progress import observed_progress

    text = observed_progress([point(1, 1, actions[0]), point(2, 1, actions[1])])[0]["text"]
    assert phrase in text and "not proof of lasting improvement" in text


def test_unknown_low_response_is_not_a_known_failed_block():
    from replay.progress import observed_progress

    text = observed_progress([point(1, 1, "blocked"), point(1, 2, "unknown"), point(2, 1, "blocked")])[0]["text"]
    assert "1 of 1 in round 1" in text


def test_throw_outcomes_use_recorded_correctness_not_just_a_button_label():
    from replay.progress import observed_progress

    decisions = [point(1, 1, "break_1", "throw_break", False),
                 point(1, 2, "break_2", "throw_break"),
                 point(2, 1, "break_2", "throw_break", True)]
    fact, = observed_progress(decisions)
    assert "0 of 1 in round 1" in fact["text"] and "1 of 1 in round 2" in fact["text"]
    assert "known outcomes" in fact["text"]
