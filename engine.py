from config import MAX_TURNS

class ConversationEngine:
    def __init__(self):
        self.sessions = {}
        self.pending_scenario = None

    # Create a dictionary key/value using call_sid as the key and details about the call session as the value
    def start_session(self, call_sid, scenario):
        self.sessions[call_sid] = {
            "scenario": scenario,
            "current_turn": 0,
            "transcript": [],
            "complete": False,
        }
        return {"action": "listen"}

    # Store agent speech in session transcript, increment the turn, and get our next utterance ready
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
        session["current_turn"] += 1

        return {"action": "send", "utterance": utterance}

    # Return transcripts for a call session using a given call_sid
    def get_transcript(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return []
        return session["transcript"]

    # Return details on a call session using a given call_sid
    def get_session(self, call_sid):
        return self.sessions.get(call_sid)

    # Mark a call session as complete given a call_sid
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