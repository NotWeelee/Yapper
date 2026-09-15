"""
Static sanity checks for generated scenarios.

A model can write a scenario that validates cleanly and still misbehaves on a
call: branches that cycle, fallback turns the main line walks into, or matching
rules that fire while the agent is behaving correctly. None of that is a
validation error, so these checks report rather than reject, and they run after
generation so a human sees them before spending a call.

The recon transcript is the thing that makes the detection checks worth
anything. A keyword or pattern that already matches what the agent said while
being helpful will fire on a clean call, and that can be tested here instead of
hoped for in the generation prompt.
"""

import re

from config import MAX_TURNS

# Fragments an agent reaches for when it is REFUSING. A keyword or pattern built
# on one of these reports a finding for a successful defence.
REFUSAL_MARKERS = (
    "can't", "cannot", "can not", "unable to", "not able to", "not permitted",
    "not allowed", "not at liberty", "have access", "outside my", "outside what",
    "i'm sorry", "i am sorry", "rather not", "not something i",
)


def check(scenario, recon_text=""):
    """
    Run every check against one scenario.

    Returns a list of (level, message), where level is "ok", "warn" or "note".
    An empty list means nothing had an opinion, which is not the same as clean.
    """
    turns = scenario.get("turns") or []
    detect = scenario.get("detect") or {}

    findings = []
    findings += check_cycles(turns)
    findings += check_fallthrough(turns)
    findings += check_turn_count(turns)
    findings += check_branch_patterns(turns, recon_text)
    findings += check_detection(detect, recon_text)
    return findings


# ---------------------------------------------------------------- turn graph

def turn_index(turns):
    return {turn["id"]: i for i, turn in enumerate(turns) if "id" in turn}


def falls_through(turn):
    """
    Whether this turn hands control to the next one when no branch matches.

    A missing 'default' behaves the same as "continue", because _resolve_branch
    starts from None and only moves off it for a default naming a turn.
    """
    branches = turn.get("branches") or []
    for branch in branches:
        if "default" in branch:
            return branch["default"] == "continue"
    return True


def build_edges(turns):
    """Every transition the engine could make, as {turn index: {target, ...}}."""
    index = turn_index(turns)
    edges = {}

    for i, turn in enumerate(turns):
        targets = set()
        for branch in turn.get("branches") or []:
            if "default" in branch:
                name = branch["default"]
                if name != "continue" and name in index:
                    targets.add(index[name])
            elif "goto" in branch and branch["goto"] in index:
                targets.add(index[branch["goto"]])

        if falls_through(turn):
            targets.add(i + 1)

        edges[i] = targets

    return edges


def check_cycles(turns):
    """
    Look for a branch cycle.

    Fall-through always moves forward, so a cycle needs at least one jump to an
    equal or lower index. That makes this exact rather than a heuristic: a walk
    of a graph this small either finds a real loop or proves there is none.
    """
    edges = build_edges(turns)
    total = len(turns)
    state = [0] * total          # 0 unvisited, 1 on the current path, 2 done
    path = []
    cycles = []

    def walk(node):
        state[node] = 1
        path.append(node)
        for target in sorted(edges.get(node, ())):
            if target >= total:
                continue          # past the last turn, the call ends
            if state[target] == 1:
                cycles.append(path[path.index(target):] + [target])
            elif state[target] == 0:
                walk(target)
        path.pop()
        state[node] = 2

    for i in range(total):
        if state[i] == 0:
            walk(i)

    if not cycles:
        return [("ok", "no branch cycles")]

    findings = []
    for cycle in cycles[:3]:
        route = " -> ".join(f"turn {i}" for i in cycle)
        findings.append((
            "warn",
            f"branch cycle {route}, which can repeat until CALL_TIMEOUT",
        ))
    return findings


def check_fallthrough(turns):
    """
    Branch targets that the main line also walks into.

    Fallback turns are written as answers to a refusal, so an agent that
    cooperates all the way through hears them as non sequiturs and the call
    spends extra turns saying them.
    """
    index = turn_index(turns)
    targets = set()

    for turn in turns:
        for branch in turn.get("branches") or []:
            name = branch.get("goto") if "goto" in branch else branch.get("default")
            if name in index:
                targets.add(index[name])

    if not targets:
        return []

    walked = sorted(i for i in targets if i > 0 and falls_through(turns[i - 1]))
    if not walked:
        return [("ok", "branch targets are reachable only by a jump")]

    listed = ", ".join(str(i) for i in walked)
    subject = f"turn {listed} is" if len(walked) == 1 else f"turns {listed} are"
    return [(
        "warn",
        f"{subject} a branch target but also runs in sequence, so an agent "
        f"that never trips a branch still hears it"
        if len(walked) == 1 else
        f"{subject} branch targets but also run in sequence, so an agent "
        f"that never trips a branch still hears them",
    )]


def check_turn_count(turns):
    if len(turns) > MAX_TURNS:
        return [(
            "warn",
            f"{len(turns)} turns but MAX_TURNS is {MAX_TURNS}, so the last "
            f"{len(turns) - MAX_TURNS} are never sent",
        )]
    return []


# ------------------------------------------------------------ recon matching

def agent_lines(recon_text):
    """The agent's side of the recon transcript, as written by transcript_text."""
    return [
        line[len("AGENT:"):].strip()
        for line in (recon_text or "").splitlines()
        if line.startswith("AGENT:")
    ]


def snippet(text, match, width=40):
    start = max(0, match.start() - 15)
    end = min(len(text), match.start() + width)
    return ("..." if start else "") + text[start:end].strip() + ("..." if end < len(text) else "")


def check_branch_patterns(turns, recon_text):
    """
    Branch patterns tested against what the agent actually said while helping.

    This is the failure that skipped a payload turn on real calls: a pattern
    built on a word like "confidential" jumps to the refusal fallback while the
    agent is busy complying. The engine matches case-insensitively against a
    single reply, so that is what gets simulated here.
    """
    lines = agent_lines(recon_text)
    if not lines:
        return []

    # The same pattern is usually repeated on every branching turn, so group by
    # pattern and report one warning naming the turns it affects.
    hits = {}
    for i, turn in enumerate(turns):
        for branch in turn.get("branches") or []:
            pattern = branch.get("match")
            if not pattern:
                continue
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue          # validate_turns already rejects these

            for line in lines:
                found = compiled.search(line)
                if found:
                    key = (pattern, branch.get("goto"))
                    hit = hits.setdefault(key, {"turns": [], "text": snippet(line, found)})
                    hit["turns"].append(i)
                    break

    findings = []
    for (pattern, goto), hit in hits.items():
        listed = ", ".join(str(i) for i in hit["turns"])
        label = f"turn {listed}" if len(hit["turns"]) == 1 else f"turns {listed}"
        findings.append((
            "warn",
            f'{label}: branch pattern matches the cooperative recon reply '
            f'"{hit["text"]}" and would jump to "{goto}" instead of continuing',
        ))

    if not findings and any("branches" in t for t in turns):
        return [("ok", "no branch pattern matches the recon transcript")]
    return findings


def check_detection(detect, recon_text):
    """Keywords and patterns that would fire on a call where nothing went wrong."""
    findings = []
    keywords = detect.get("keywords") or []
    patterns = detect.get("patterns") or []

    # Mirror the analyzer: keywords are substring matches and patterns are
    # regexes, both case-insensitive over the agent's replies joined together.
    lines = agent_lines(recon_text)
    blob = " ".join(lines)

    if blob:
        for keyword in keywords:
            if str(keyword).lower() in blob.lower():
                findings.append((
                    "warn",
                    f'keyword "{keyword}" already appears in the recon '
                    f"transcript, so it fires on a clean call",
                ))

        for pattern in patterns:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                continue
            found = compiled.search(blob)
            if found:
                findings.append((
                    "warn",
                    f'pattern "{pattern}" matches the recon transcript at '
                    f'"{snippet(blob, found)}", where the agent was cooperating',
                ))

    for keyword in keywords:
        lowered = str(keyword).lower()
        if any(marker in lowered for marker in REFUSAL_MARKERS):
            findings.append((
                "note",
                f'keyword "{keyword}" reads as refusal language, which is what '
                f"the agent says when it behaves correctly",
            ))

    return findings
