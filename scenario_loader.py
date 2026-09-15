import os
import re
import yaml
from config import SCENARIO_DIR

REQUIRED_FIELDS = ["name", "category", "owasp_id", "severity", "description", "turns", "detect"]

# The only keys a detect block may carry. Anything else is a typo or, more
# often, malformed output from a model that generated the scenario.
DETECT_KEYS = {"keywords", "patterns", "llm_judge"}

# Severity is only ever displayed, so an unexpected value does not surface
# until the report is printed, which is after every call has been spent.
SEVERITIES = ("low", "medium", "high", "critical")

class ScenarioLoader:
    def __init__(self, scenario_dir=SCENARIO_DIR):
        self.scenario_dir = scenario_dir

    # Read Scenario YAML files and add each scenarios to the scenario list
    # Returns the list of scenarios
    def load_all(self):
        scenarios = []

        if not os.path.exists(self.scenario_dir):
            print(f"Warning: scenario directory not found: {self.scenario_dir}")
            return scenarios

        for filename in sorted(os.listdir(self.scenario_dir)):
            if not filename.endswith(".yaml"):
                continue
            filepath = os.path.join(self.scenario_dir, filename)
            try:
                scenario = self.parse_file(filepath)
                scenarios.append(scenario)
            except Exception as e:
                print(f"Warning: skipping {filepath}: {e}")

        return scenarios
    

    # Read each YAML file and confirm that they are formatted correctly
    # If the detect block doesn't exist, fill them with empty/null values
    def parse_file(self, filepath):
        with open(filepath) as f:
            data = yaml.safe_load(f)

        return self.validate(data)

    # Validate an already-parsed scenario. Split out from parse_file so generated
    # scenarios can be checked before anything is written to disk.
    @classmethod
    def validate(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Scenario must be a mapping")

        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        severity = data["severity"]
        if not isinstance(severity, str) or severity.lower() not in SEVERITIES:
            raise ValueError(
                f"'severity' must be one of {', '.join(SEVERITIES)}, "
                f"got {severity!r}"
            )

        cls.validate_turns(data["turns"])
        cls.validate_detect(data["detect"])

        detect = data["detect"]
        detect.setdefault("keywords", [])
        detect.setdefault("patterns", [])
        detect.setdefault("llm_judge", None)

        return data

    # Check the detect block. Every rule here exists because a malformed block
    # would otherwise load cleanly and then misbehave during a scan: a bad regex
    # warns on every turn, a judge with no prompt raises mid-call, and a block
    # with nothing in it can never report anything at all.
    @staticmethod
    def validate_detect(detect):
        if not isinstance(detect, dict):
            raise ValueError("'detect' must be a mapping")

        unknown = set(detect) - DETECT_KEYS
        if unknown:
            raise ValueError(
                "Unknown key(s) in detect: %s" % ", ".join(repr(k) for k in sorted(unknown))
            )

        for field in ("keywords", "patterns"):
            values = detect.get(field)
            if values is None:
                continue
            if not isinstance(values, list):
                raise ValueError(f"'{field}' must be a list")
            for v in values:
                if not isinstance(v, str) or not v.strip():
                    raise ValueError(f"'{field}' contains an empty or non-string entry: {v!r}")

        for pattern in detect.get("patterns") or []:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex in patterns: {pattern!r} ({e})")

        judge = detect.get("llm_judge")
        if judge is not None:
            if not isinstance(judge, dict):
                raise ValueError("'llm_judge' must be a mapping")
            prompt = judge.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                raise ValueError("'llm_judge' needs a non-empty 'prompt'")
            threshold = judge.get("finding_threshold", 7)
            if not isinstance(threshold, (int, float)) or isinstance(threshold, bool)                     or not 0 < threshold <= 10:
                raise ValueError(
                    f"'finding_threshold' must be a number above 0 and at most 10, got {threshold!r}"
                )

        if not (detect.get("keywords") or detect.get("patterns") or judge):
            raise ValueError("'detect' has no keywords, patterns or llm_judge, so it can never fire")

    # Check a scripted scenario's turns: every turn speaks, and every branch
    # points at a turn 'id' that actually exists (the engine warns and falls
    # through at runtime, but a typo is better caught at load time)
    @staticmethod
    def validate_turns(turns):
        if not turns:
            raise ValueError("'turns' is empty")

        turn_ids = {turn["id"] for turn in turns if "id" in turn}

        for i, turn in enumerate(turns):
            if "send" not in turn:
                raise ValueError(f"Turn {i} missing 'send' field")

            for branch in turn.get("branches", []):
                if "default" in branch:
                    target = branch["default"]
                    if target != "continue" and target not in turn_ids:
                        raise ValueError(
                            f"Turn {i} default branch targets unknown turn id: {target}"
                        )
                    continue

                if "match" not in branch or "goto" not in branch:
                    raise ValueError(
                        f"Turn {i} branch needs both 'match' and 'goto' (or 'default')"
                    )
                try:
                    re.compile(branch["match"])
                except re.error as e:
                    raise ValueError(f"Turn {i} branch has invalid regex: {e}")
                if branch["goto"] not in turn_ids:
                    raise ValueError(
                        f"Turn {i} branch targets unknown turn id: {branch['goto']}"
                    )

    # Create a summary for each scenario (based on YAML) and returns it
    # Used for --list-scenarios to see what scenarios are available
    def list_all(self):
        result = []
        for s in self.load_all():
            summary = {
                "name": s["name"],
                "category": s["category"],
                "owasp_id": s["owasp_id"],
                "severity": s["severity"],
                "description": s["description"],
            }
            result.append(summary)
        return result

    # Return a scenario if the input string matches the name of an existing scenario
    def get_by_name(self, name):
        for s in self.load_all():
            if s["name"] == name:
                return s
        return None

    # Return scenario(s) if the input string matches the category of an existing scenario
    def get_by_category(self, category):
        return [s for s in self.load_all() if s["category"] == category]

    # Return all scenarios
    def get_all(self):
        return self.load_all()