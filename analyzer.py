import re
import json
import anthropic
from config import ANTHROPIC_API_KEY, JUDGE_MODEL


class Analyzer:
    def __init__(self, use_judge=True):
        self.use_judge = use_judge
        if use_judge and ANTHROPIC_API_KEY:
            self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        else:
            self.client = None
            if use_judge:
                print("Warning: no ANTHROPIC_API_KEY set, skipping LLM judge")
                self.use_judge = False

    # Check if the AI agent said something they shouldn't have
    def analyze(self, scenario, transcript):
        detect = scenario["detect"]
        agent_responses = [
            t["content"] for t in transcript if t["role"] == "agent"
        ]
        full_text = " ".join(agent_responses)

        findings = []

        # Tier 1: keyword detection
        # If specific keywords specified in the scenario YAML as an 'agent fail' is found,
        # add the agent response that contains the keyword to the findings list 
        for keyword in detect.get("keywords", []):
            if keyword.lower() in full_text.lower():
                findings.append({
                    "type": "keyword",
                    "value": keyword,
                    "context": self.extract_context(full_text, keyword),
                })

        # Tier 2: regex pattern detection
        # If specific patterns specified in the scenario YAML as an 'agent fail' is found,
        # add the agent response that contains the keyword to the findings list
        for pattern in detect.get("patterns", []):
            try:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    findings.append({
                        "type": "pattern",
                        "value": pattern,
                        "match": match.group(0)[:200],
                    })
            except re.error:
                print(f"Warning: invalid regex pattern: {pattern}")

        # Tier 3: LLM judge
        # If LLM judge prompt is specified in scenario YAML as an 'agent fail',
        # send the prompt with the transcript to the LLM to check if there is a potential fail
        judge_result = None
        if self.use_judge and detect.get("llm_judge"):
            judge_result = self.run_judge(detect["llm_judge"], transcript)
            if judge_result and judge_result.get("finding"):
                findings.append({
                    "type": "llm_judge",
                    "confidence": judge_result.get("confidence", 0),
                    "reasoning": judge_result.get("reasoning", ""),
                })

        return {
            "scenario": scenario["name"],
            "category": scenario["category"],
            "owasp_id": scenario["owasp_id"],
            "severity": scenario["severity"],
            "description": scenario["description"],
            "triggered": len(findings) > 0,
            "findings": findings,
            "judge_result": judge_result,
            "transcript": transcript,
        }

    # Send the entire transcript with the LLM judge prompt specified in your scenario YAML
    def run_judge(self, judge_config, transcript):
        prompt = judge_config["prompt"]
        threshold = judge_config.get("finding_threshold", 7)

        # Build transcript text for the judge
        transcript_text = ""
        for entry in transcript:
            role = "CALLER" if entry["role"] == "user" else "AGENT"
            transcript_text += f"{role}: {entry['content']}\n"

        full_prompt = f"{prompt}\n\nTranscript:\n{transcript_text}"

        try:
            message = self.client.messages.create(
                model=JUDGE_MODEL,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": full_prompt}
                ],
            )

            response_text = message.content[0].text

            # Try to parse JSON from the response
            cleaned = response_text.strip()
            # Handle cases where the model wraps JSON in markdown
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()

            result = json.loads(cleaned)

            # Apply threshold
            confidence = result.get("confidence", 0)
            if confidence >= threshold:
                result["finding"] = True
            else:
                result["finding"] = False

            return result

        except json.JSONDecodeError as e:
            print(f"Warning: could not parse judge response as JSON: {e}")
            return {"finding": False, "reasoning": "Failed to parse response"}
        except Exception as e:
            print(f"Warning: LLM judge failed: {e}")
            return {"finding": False, "reasoning": str(e)}

    # Creates a snippet surrounding a 'keyword' specific in the scenario YAML if the keyword is found
    def extract_context(self, text, needle, window=80):
        idx = text.lower().find(needle.lower())
        if idx == -1:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(needle) + window)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        return snippet