import json
from datetime import datetime, timezone
from pathlib import Path


class Reporter:
    def __init__(self, results, target_number=""):
        self.results = results
        self.target_number = target_number
        self.timestamp = datetime.now(timezone.utc).isoformat()

    @property
    def findings(self):
        return [r for r in self.results if r["triggered"]]

    @property
    def passed(self):
        return [r for r in self.results if not r["triggered"]]

    def print_summary(self):
        total = len(self.results)
        n_findings = len(self.findings)
        n_passed = len(self.passed)

        print()
        print("=" * 60)
        print("  Yapper Results Summary")
        print("=" * 60)
        print(f"  Target:     {self.target_number}")
        print(f"  Timestamp:  {self.timestamp}")
        print(f"  Scenarios:  {total}")
        print(f"  Findings:   {n_findings}")
        print(f"  Passed:     {n_passed}")
        print()

        if self.findings:
            print("  FINDINGS:")
            print("  " + "-" * 56)
            for r in self.findings:
                severity = r["severity"].upper()
                print(f"  [{severity}] {r['scenario']}")
                print(f"    OWASP: {r['owasp_id']}")
                print(f"    {r['description']}")

                for finding in r.get("findings", []):
                    ftype = finding["type"]

                    if ftype == "keyword":
                        print(f"    -> Keyword match: {finding['value']}")
                        if finding.get("context"):
                            context = finding["context"][:100]
                            print(f"       {context}")

                    elif ftype == "pattern":
                        print(f"    -> Pattern match: {finding['value']}")
                        if finding.get("match"):
                            print(f"       Matched: {finding['match'][:100]}")

                    elif ftype == "llm_judge":
                        confidence = finding.get("confidence", "?")
                        print(f"    -> LLM Judge (confidence: {confidence}/10)")
                        if finding.get("reasoning"):
                            reasoning = finding["reasoning"][:200]
                            print(f"       {reasoning}")

                print()

        if self.passed:
            print("  PASSED:")
            print("  " + "-" * 56)
            for r in self.passed:
                print(f"  {r['scenario']}")
            print()

        print("=" * 60)

    def print_transcripts(self):
        for r in self.results:
            print(f"\n--- {r['scenario']} ---")
            for entry in r.get("transcript", []):
                role = "AGENT" if entry["role"] == "agent" else "USER "
                print(f"  [{role}] {entry['content']}")
            print()

    def to_dict(self):
        return {
            "meta": {
                "tool": "yapper",
                "version": "0.1.0",
                "timestamp": self.timestamp,
                "target_number": self.target_number,
            },
            "summary": {
                "total": len(self.results),
                "findings": len(self.findings),
                "passed": len(self.passed),
            },
            "results": self.results,
        }

    def write_json(self, path):
        path = Path(path)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)