from flask import Flask, request
from twilio.twiml.voice_response import VoiceResponse, Gather
from config import SPEECH_TIMEOUT, SPEECH_LANGUAGE, SPEECH_MODEL
from engine import ConversationEngine
from scenario_loader import ScenarioLoader

app = Flask(__name__)
engine = ConversationEngine()
loader = ScenarioLoader()


@app.route("/call/start", methods=["POST"])
def call_start():
    call_sid = request.form["CallSid"]

    scenario = engine.pending_scenario
    if not scenario:
        response = VoiceResponse()
        response.say("No scenario configured.")
        response.hangup()
        return str(response), 200, {"Content-Type": "text/xml"}

    result = engine.start_session(call_sid, scenario)

    return build_twiml(result)


@app.route("/call/turn", methods=["POST"])
def call_turn():
    call_sid = request.form["CallSid"]
    agent_speech = request.form.get("SpeechResult", "")
    confidence = request.form.get("Confidence", "")

    result = engine.handle_response(call_sid, agent_speech, confidence)

    return build_twiml(result)


@app.route("/call/status", methods=["POST"])
def call_status():
    call_sid = request.form["CallSid"]
    status = request.form.get("CallStatus", "")

    print(f"Call {call_sid} ended with status: {status}")

    # Dump transcript if we have one
    transcript = engine.get_transcript(call_sid)
    if transcript:
        print(f"\n--- Transcript for {call_sid} ---")
        for entry in transcript:
            role = "AGENT" if entry["role"] == "agent" else "USER"
            print(f"  [{role}] {entry['content']}")
        print()

    # Mark session as complete
    session = engine.get_session(call_sid)
    if session:
        session["complete"] = True

    return "", 204


def build_twiml(result):
    response = VoiceResponse()

    if result["action"] == "listen":
        gather = Gather(
            input="speech",
            action="/call/turn",
            method="POST",
            speech_timeout=SPEECH_TIMEOUT,
            speech_model=SPEECH_MODEL,
            language=SPEECH_LANGUAGE
        )
        response.append(gather)
        response.redirect("/call/turn")

    elif result["action"] == "send":
        gather = Gather(
            input="speech",
            action="/call/turn",
            method="POST",
            speech_timeout=SPEECH_TIMEOUT,
            speech_model=SPEECH_MODEL,
            language=SPEECH_LANGUAGE,
            enhanced="true"
        )
        gather.say(result["utterance"])
        response.append(gather)
        response.redirect("/call/turn")

    elif result["action"] == "hangup":
        response.say("Thank you, goodbye.")
        response.hangup()

    return str(response), 200, {"Content-Type": "text/xml"}