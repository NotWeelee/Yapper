from config import MAX_TURNS
import re


class ConversationEngine:
    def __init__(self):
        self.sessions = {}
        self.pending_scenario = None

    # Create a dictionary key/value using call_sid as the key and details about the call session as the value
    def start_session(self, call_sid, scenario):
        is_adaptive = "strategy" in scenario

        # Build turn index for branching (scripted scenarios only)
        turn_index = {}
        if not is_adaptive:
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
            "adaptive": is_adaptive,
        }
        return {"action": "listen"}

    # Store agent speech in session transcript and get our next utterance ready
    def handle_response(self, call_sid, agent_speech="", confidence=""):
        session = self.sessions.get(call_sid)

        if not session:
            return {"action": "hangup"}

        # Store what the agent just said
        if agent_speech:
            session["transcript"].append({
                "role": "agent",
                "content": agent_speech,
                "confidence": confidence,
                "turn": session["current_turn"],
            })

        # If we haven't heard the agent speak yet, keep listening
        if not agent_speech and not session["transcript"]:
            return {"action": "listen"}
        
        # If we sent something last turn but got no response, keep listening
        if not agent_speech and session["transcript"] and session["transcript"][-1]["role"] == "user":
            return {"action": "listen"}

        # Route to the appropriate handler
        if session["adaptive"]:
            return self._handle_adaptive(session)
        else:
            return self._handle_scripted(session)

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

        # Get next utterance and apply templates
        utterance = total_turns[current_turn]["send"]
        utterance = self.apply_templates(utterance, session["transcript"])

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

    # Handle adaptive scenarios using LLM-generated utterances
    def _handle_adaptive(self, session):
        strategy = session["scenario"]["strategy"]
        max_turns = strategy.get("max_turns", 6)
        current_turn = session["current_turn"]

        # Check if we're done
        if current_turn >= max_turns or current_turn >= MAX_TURNS:
            session["complete"] = True
            return {"action": "hangup"}

        # Import here to avoid loading the module when not using adaptive scenarios.
        # strategist.py is kept out of the public repo for now.
        try:
            from strategist import generate_utterance
        except ImportError:
            raise RuntimeError(
                "This scenario uses adaptive strategy generation, which requires "
                "strategist.py (not included in this build)."
            )

        utterance = generate_utterance(
            strategy=strategy,
            transcript=session["transcript"],
            turn_number=current_turn,
        )

        # Log our utterance
        session["transcript"].append({
            "role": "user",
            "content": utterance,
            "turn": current_turn,
        })

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

    # Remove call session using a given call_sid
    def remove_session(self, call_sid):
        return self.sessions.pop(call_sid, None)

    # Sets the last response in a variable that can be used if
    # the {{last_response}} tag exists in the scenario YAML
    def apply_templates(self, message, transcript):
        # {{last_response}} - most recent agent response
        last_response = ""
        for entry in reversed(transcript):
            if entry["role"] == "agent":
                last_response = entry["content"]
                break

        message = message.replace("{{last_response}}", last_response)

        # {{turn_count}} - number of user turns so far
        turn_count = sum(1 for t in transcript if t["role"] == "user")
        message = message.replace("{{turn_count}}", str(turn_count))

        return message