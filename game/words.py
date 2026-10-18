from game.state import DOWNED_BIT, JUGGLED_BIT, JUGGLED_STATE

RECENT_WINDOW = 120
CROUCH_BIT = 0x1
LOW_GUARD_BIT = 0x8
STAND_GUARD_BIT = 0x10
PASSIVE_GUARD_BIT = 0x100
AIRBORNE_STATES = (24, 25, 26, 27)
CROUCH_STATES = (5, 6, 7)
DISTANCE_WORDS = {"point_blank": "touching the bot", "close": "at close range", "mid": "at mid range", "far": "far away", "very_far": "far away"}
ACTION_WORDS = {
    "press": "pressed a button after blocking",
    "block_high": "stood and blocked after blocking",
    "block_low": "crouch-blocked after blocking",
    "duck": "ducked after blocking",
    "ss_left": "sidestepped left after blocking",
    "ss_right": "sidestepped right after blocking",
    "backdash": "backed away after blocking",
    "throw": "went for a throw after blocking",
    "hit": "got hit by a low",
    "blocked": "blocked a low",
    "low_parry": "parried a low",
    "jumped": "jumped over a low",
    "break_1": "broke a throw",
    "break_2": "broke a throw",
    "break_12": "broke a throw",
    "left": "sidestepped left",
    "right": "sidestepped right",
}
HEALTH_PHRASES = {"healthy": "is healthy", "low": "has low health", "critical": "has critical health"}
EVENT_WORDS = {
    "hit": "landed a hit",
    "counter_hit": "landed a counter hit",
    "block": "had a move blocked",
    "whiff": "whiffed a move",
    "throw": "went for a throw",
    "throw_break": "broke a throw",
    "knockdown": "scored a knockdown",
}


def distance_words(bucket):
    return DISTANCE_WORDS.get(bucket, "at mid range")


def frame_words(advantage):
    if advantage is None:
        return None
    if advantage <= -10:
        return "a big disadvantage"
    if advantage < 0:
        return "a small disadvantage"
    if advantage == 0:
        return "even frames"
    if advantage < 10:
        return "a small advantage"
    return "a big advantage"


def lead_words(own, other):
    scale = max(own["max_health"], 1)
    diff = (own["health"] - other["health"]) / scale
    if diff >= 0.35:
        return "far ahead"
    if diff >= 0.10:
        return "ahead"
    if diff <= -0.35:
        return "far behind"
    if diff <= -0.10:
        return "behind"
    return "even"


def health_words(player):
    frac = player["health"] / max(player["max_health"], 1)
    if frac <= 0.2:
        return "critical"
    if frac < 0.5:
        return "low"
    return "healthy"


def stance_words(player):
    status = player.get("status", 0)
    basic = player.get("basic_state", 3)
    if player.get("being_thrown", "none") != "none":
        return "being thrown"
    if status & DOWNED_BIT:
        return "on the ground"
    if status & JUGGLED_BIT or basic == JUGGLED_STATE:
        return "being juggled"
    if basic in AIRBORNE_STATES:
        return "in the air"
    if player["hit_level"] != "none" and not player["free_movement"]:
        return "attacking"
    if status & LOW_GUARD_BIT or status & CROUCH_BIT or basic in CROUCH_STATES:
        return "crouching"
    if status & STAND_GUARD_BIT and not status & PASSIVE_GUARD_BIT:
        return "blocking"
    return "standing"


def timer_words(timer_s):
    if timer_s is None:
        return None
    if timer_s > 45:
        return "early in the round"
    if timer_s > 20:
        return "midway through the round"
    if timer_s > 8:
        return "late in the round"
    return "the final seconds of the round"


def flag_words(player):
    flags = []
    if player.get("heat_active"):
        flags.append("heat active")
    elif not player.get("heat_used") and player.get("heat_gauge", 0) == 0:
        flags.append("heat available")
    if player.get("rage_active"):
        flags.append("rage active")
    return flags


def recent_words(events, opponent, frame, round_):
    if not events:
        return None
    for ev in reversed(events):
        if ev.get("t") != "event" or ev.get("round") != round_ or ev.get("actor") != opponent:
            continue
        if frame - ev.get("frame", frame) > RECENT_WINDOW or ev.get("frame", 0) > frame:
            continue
        if ev.get("kind") == "decision_point":
            words = ACTION_WORDS.get(ev.get("action"))
        else:
            words = EVENT_WORDS.get(ev.get("kind"))
        if words:
            return f"Recently the opponent {words}."
    return None


def state_sentence(state, recent_events=None):
    human = state["human_slot"]
    opp, bot = state["players"][human], state["players"][1 - human]
    derived = state["derived"]
    sentences = []
    recent = recent_words(recent_events, human, state["frame"], state["round"])
    if recent:
        sentences.append(recent)
    frame = frame_words(derived.get("frame_advantage"))
    stance = stance_words(opp)
    where = distance_words(derived.get("distance_bucket"))
    if frame:
        sentences.append(f"The opponent is at {frame}, {stance} {where}.")
    else:
        sentences.append(f"The opponent is {stance} {where}.")
    opp_flags = flag_words(opp)
    bot_flags = flag_words(bot)
    opp_text = f"The opponent {HEALTH_PHRASES[health_words(opp)]}" + (" with " + " and ".join(opp_flags) if opp_flags else "") + "."
    bot_text = f"The bot {HEALTH_PHRASES[health_words(bot)]}" + (" with " + " and ".join(bot_flags) if bot_flags else "") + "."
    sentences.append(opp_text + " " + bot_text)
    lead = lead_words(bot, opp)
    sentences.append("The bot is even on health." if lead == "even" else f"The bot is {lead} on health.")
    timer = timer_words(derived.get("timer_s"))
    if timer:
        sentences.append(f"It is {timer}.")
    sentences.append("The stage is open.")
    return " ".join(sentences)
