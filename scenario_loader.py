import os
import yaml
from config import SCENARIO_DIR

REQUIRED_FIELDS = ["name", "category", "owasp_id", "severity", "description", "turns", "detect"]

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

        for field in REQUIRED_FIELDS:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        for i, turn in enumerate(data["turns"]):
            if "send" not in turn:
                raise ValueError(f"Turn {i} missing 'send' field")

        detect = data["detect"]
        detect.setdefault("keywords", [])
        detect.setdefault("patterns", [])
        detect.setdefault("llm_judge", None)

        return data

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