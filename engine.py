from config import MAX_TURNS, MAX_CONTINUATIONS
import re
import time

# Twilio punctuates its transcripts, so a response that doesn't land on one of
# these was almost certainly cut off mid-sentence by the 60 second Gather cap.
TERMINAL_PUNCTUATION = ".?!"


class ConversationEngine:
    def __init__(self):
        self.sessions = {}
        self.pending_scenario = None

    # Create a dictionary key/value using call_sid as the key and details about the call session as the value
    def start_session(self, call_sid, scenario):
        # Build turn index for branching
        turn_index = {}
        for i, turn in enumerate(scenario.get("turns", [])):
            if "id" in turn:
                turn_index[turn["id"]] = i

        self.sessions[call_sid] = {
            "scenario": scenario,
            "current_turn": 0,
            "turn_index": turn_index,
            "last_sent_turn": None,
            "transcript": [],
            "complete": False,
            "continuations": 0,
            "last_activity": time.time(),
        }
        return {"action": "listen"}

    # Store agent speech in session transcript and get our next utterance ready
    def handle_response(self, call_sid, agent_speech="", confidence=""):
        session = self.sessions.get(call_sid)

        if not session:
            return {"action": "hangup"}

        # Any webhook at all means the call is still alive. The gap since the
        # last one is how long this gather ran, recorded so truncation against
        # Twilio's 60 second cap can be measured rather than inferred.
        now = time.time()
        gather_seconds = round(now - session["last_activity"], 1)
        session["last_activity"] = now

        # Store what the agent just said
        if agent_speech:
            self.record_agent_speech(session, agent_speech, confidence, gather_seconds)

        # If we haven't heard the agent speak yet, keep listening
        if not agent_speech and not session["transcript"]:
            return {"action": "listen"}
        
        # If we sent something last turn but got no response, keep listening
        if not agent_speech and session["transcript"] and session["transcript"][-1]["role"] == "user":
            return {"action": "listen"}

        # If the agent was cut off mid-sentence, open another silent gather and
        # collect the rest rather than talking over the end of their answer.
        # Silence ends the chain on its own: an empty result falls through to the
        # handlers below and the scenario carries on as normal.
        if agent_speech and self.should_extend(session, agent_speech):
            session["continuations"] += 1
            return {"action": "listen"}

        session["continuations"] = 0

        return self._handle_scripted(session)

    # Append agent speech to the transcript. While a turn is being extended the
    # incoming text is a continuation of the answer already recorded, so it is
    # merged into that entry instead of becoming a phantom turn of its own.
    def record_agent_speech(self, session, agent_speech, confidence, gather_seconds=None):
        transcript = session["transcript"]

        if session["continuations"] and transcript and transcript[-1]["role"] == "agent":
            previous = transcript[-1]
            previous["content"] = previous["content"].rstrip() + " " + agent_speech
            previous["continuations"] = session["continuations"]
            previous["gather_seconds"].append(gather_seconds)
            return

        transcript.append({
            "role": "agent",
            "content": agent_speech,
            "confidence": confidence,
            "turn": session["current_turn"],
            "gather_seconds": [gather_seconds],
        })

    # Decide whether to spend another gather collecting the rest of an answer.
    # Bounded by MAX_CONTINUATIONS so an agent that never punctuates cannot hold
    # the call open indefinitely, since extending does not advance current_turn
    # and so is not covered by MAX_TURNS.
    def should_extend(self, session, agent_speech):
        if session["continuations"] >= MAX_CONTINUATIONS:
            return False

        text = agent_speech.rstrip()
        return bool(text) and text[-1] not in TERMINAL_PUNCTUATION

    # Handle scripted scenarios with optional branching
    def _handle_scripted(self, session):
        # If the last turn had branches, evaluate them against the agent's response
        if session["last_sent_turn"] is not None:
            last_agent_speech = ""
            for entry in reversed(session["transcript"]):
                if entry["role"] == "agent":
                    last_agent_speech = entry["content"]
                    break

            if last_agent_speech:
                last_turn = session["scenario"]["turns"][session["last_sent_turn"]]
                if "branches" in last_turn:
                    resolved = self._resolve_branch(
                        last_turn["branches"],
                        last_agent_speech,
                        session["turn_index"],
                    )
                    if resolved is not None:
                        session["current_turn"] = resolved

        total_turns = session["scenario"]["turns"]
        current_turn = session["current_turn"]

        # Check if we're done
        if current_turn >= len(total_turns) or current_turn >= MAX_TURNS:
            session["complete"] = True
            return {"action": "hangup"}

        # Get next utterance
        utterance = total_turns[current_turn]["send"]

        # Log our utterance
        session["transcript"].append({
            "role": "user",
            "content": utterance,
            "turn": current_turn,
        })

        # Track for branch evaluation next round
        session["last_sent_turn"] = current_turn
        session["current_turn"] = current_turn + 1

        return {"action": "send", "utterance": utterance}

    def _resolve_branch(self, branches, agent_speech, turn_index):
        """
        Evaluate branch conditions against agent speech.
        Returns the turn index to jump to, or None to continue sequentially.
        """
        default_action = None

        for branch in branches:
            # Handle default branch
            if "default" in branch:
                if branch["default"] == "continue":
                    default_action = None
                elif branch["default"] in turn_index:
                    default_action = turn_index[branch["default"]]
                continue

            # Handle match -> goto branch
            if "match" in branch and "goto" in branch:
                if re.search(branch["match"], agent_speech, re.IGNORECASE):
                    target = branch["goto"]
                    if target in turn_index:
                        return turn_index[target]
                    else:
                        print(f"Warning: branch target '{target}' not found, continuing")
                        return None

        return default_action

    # Return transcripts for a call session using a given call_sid
    def get_transcript(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return []
        return session["transcript"]

    # Return details on a call session using a given call_sid
    def get_session(self, call_sid):
        return self.sessions.get(call_sid)

    # Check if a call session is complete given a call_sid
    def is_complete(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return False
        return session["complete"]

    # Seconds since the last webhook for this call, or None if there is no session.
    # Used to tell a slow call apart from a dead one.
    def seconds_since_activity(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return None
        return time.time() - session["last_activity"]

    # Remove call session using a given call_sid
    def remove_session(self, call_sid):
        return self.sessions.pop(call_sid, None)

