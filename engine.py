from config import MAX_TURNS

class ConversationEngine:
    def __init__(self):
        self.sessions = {}
        self.pending_scenario = None

    def start_session(self, call_sid, scenario):
        self.sessions[call_sid] = {
            "scenario": scenario,
            "current_turn": 0,
            "transcript": [],
            "complete": False,
        }
        return {"action": "listen"}

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

        turns = session["scenario"]["turns"]
        current = session["current_turn"]

        # Check if we're done
        if current >= len(turns) or current >= MAX_TURNS:
            session["complete"] = True
            return {"action": "hangup"}

        # Get next utterance and apply templates
        utterance = turns[current]["send"]
        utterance = self._apply_templates(utterance, session["transcript"])

        # Log our utterance
        session["transcript"].append({
            "role": "user",
            "content": utterance,
            "turn": current,
        })
        session["current_turn"] += 1

        return {"action": "send", "utterance": utterance}

    def get_transcript(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return []
        return session["transcript"]

    def get_session(self, call_sid):
        return self.sessions.get(call_sid)

    def is_complete(self, call_sid):
        session = self.sessions.get(call_sid)
        if not session:
            return True
        return session["complete"]

    def remove_session(self, call_sid):
        return self.sessions.pop(call_sid, None)

    def _apply_templates(self, message, transcript):
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