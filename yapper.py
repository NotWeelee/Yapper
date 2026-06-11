#!/usr/bin/env python3
"""
Yapper - Voice AI Agent Security Testing Tool
"""

import argparse
import sys
import threading
import time

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    TWILIO_PHONE_NUMBER,
    WEBHOOK_BASE_URL,
    WEBHOOK_PORT,
    ANTHROPIC_API_KEY,
)
from scenario_loader import ScenarioLoader
from engine import ConversationEngine
from caller import initiate_call
from analyzer import Analyzer
from reporter import Reporter


def build_parser():
    parser = argparse.ArgumentParser(
        prog="yapper",
        description="Security testing tool for voice-based AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  # List all available scenarios
  python yapper.py --list-scenarios

  # Run all scenarios against a target phone number
  python yapper.py --target +15559876543 --all

  # Run a specific scenario
  python yapper.py --target +15559876543 --scenario prompt_injection_canary

  # Run all scenarios in a category
  python yapper.py --target +15559876543 --category LLM01_prompt_injection

  # Run without the LLM judge
  python yapper.py --target +15559876543 --all --no-judge

  # Verbose output with full transcripts
  python yapper.py --target +15559876543 --all --verbose

  # Save JSON report
  python yapper.py --target +15559876543 --all --output report.json
        """,
    )

    target_group = parser.add_argument_group("target")
    target_group.add_argument(
        "--target",
        help="Phone number of the target voice AI agent (e.g. +15559876543)",
    )

    scenario_group = parser.add_argument_group("scenario selection")
    scenario_group.add_argument(
        "--all",
        action="store_true",
        help="Run all available scenarios",
    )
    scenario_group.add_argument(
        "--scenario",
        action="append",
        dest="scenarios",
        help="Run a specific scenario by name (can be repeated)",
    )
    scenario_group.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="Run all scenarios in a category (can be repeated)",
    )
    scenario_group.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List all available scenarios and exit",
    )

    output_group = parser.add_argument_group("output")
    output_group.add_argument(
        "--output", "-o",
        help="Write JSON report to file",
    )
    output_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show full conversation transcripts",
    )
    output_group.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge analysis, only use pattern matching",
    )

    return parser


def validate_config(use_judge=True):
    missing = []

    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_PHONE_NUMBER:
        missing.append("TWILIO_PHONE_NUMBER")
    if not WEBHOOK_BASE_URL:
        missing.append("WEBHOOK_BASE_URL")
    if use_judge and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    if missing:
        print("Error: missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nSet these in your .env file or environment.")
        sys.exit(1)


def resolve_scenarios(loader, args):
    if args.all:
        return loader.get_all()

    selected = []

    if args.scenarios:
        for name in args.scenarios:
            scenario = loader.get_by_name(name)
            if scenario:
                selected.append(scenario)
            else:
                print(f"Warning: scenario '{name}' not found")

    if args.categories:
        for category in args.categories:
            matches = loader.get_by_category(category)
            if matches:
                selected.extend(matches)
            else:
                print(f"Warning: no scenarios found in category '{category}'")

    return selected


def start_webhook_server():
    from webhook import app

    # Silence Flask startup banner
    import flask.cli
    flask.cli.show_server_banner = lambda *args: None
    
    app.run(port=WEBHOOK_PORT, debug=False, use_reloader=False)


def wait_for_call_completion(engine, call_sid, timeout=300):
    elapsed = 0
    interval = 2

    while elapsed < timeout:
        if engine.is_complete(call_sid):
            return True
        time.sleep(interval)
        elapsed += interval

    print(f"Warning: call {call_sid} timed out after {timeout} seconds")
    return False


def main():
    parser = build_parser()
    args = parser.parse_args()

    loader = ScenarioLoader()

    # List scenarios and exit
    if args.list_scenarios:
        scenarios = loader.list_all()
        if not scenarios:
            print("No scenarios found.")
            return 0

        print(f"\n{'NAME':<45} {'CATEGORY':<35} {'SEVERITY':<10}")
        print("-" * 90)
        for s in scenarios:
            print(f"{s['name']:<45} {s['category']:<35} {s['severity']:<10}")
        print(f"\n{len(scenarios)} scenario(s) available.\n")
        return 0

    # Validate target
    if not args.target:
        parser.error("--target is required (unless using --list-scenarios)")

    # Resolve scenarios
    selected = resolve_scenarios(loader, args)
    if not selected:
        parser.error("No scenarios selected. Use --all, --scenario, or --category.")

    # Validate config
    use_judge = not args.no_judge
    validate_config(use_judge=use_judge)

    # Print header
    print(f"\n  Yapper - Voice AI Security Testing")
    print(f"  Target:    {args.target}")
    print(f"  Scenarios: {len(selected)}")
    print(f"  Judge:     {'enabled' if use_judge else 'disabled'}")
    print()

    # Start webhook server in background thread
    webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
    webhook_thread.start()
    time.sleep(2)  # give the server a moment to start

    # Initialize engine and analyzer
    from webhook import engine
    analyzer = Analyzer(use_judge=use_judge)

    # Run each scenario
    results = []
    for i, scenario in enumerate(selected, 1):
        print(f"[{i}/{len(selected)}] Running: {scenario['name']}")

        # Tell the engine which scenario to use for the next call
        engine.pending_scenario = scenario

        # Place the call
        call_sid = initiate_call(
            account_sid=TWILIO_ACCOUNT_SID,
            auth_token=TWILIO_AUTH_TOKEN,
            from_number=TWILIO_PHONE_NUMBER,
            to_number=args.target,
            webhook_base_url=WEBHOOK_BASE_URL,
        )

        # Wait for the call to finish
        if not wait_for_call_completion(engine, call_sid):
            print(f"  Skipping analysis for timed out call")
            continue

        # Analyze the transcript
        transcript = engine.get_transcript(call_sid)
        result = analyzer.analyze(scenario, transcript)
        results.append(result)

        status = "FINDING" if result["triggered"] else "PASS"
        print(f"  -> {status}")

        if args.verbose:
            for entry in transcript:
                role = "AGENT" if entry["role"] == "agent" else "USER"
                print(f"     [{role}] {entry['content']}")
            print()

        # Clean up
        engine.remove_session(call_sid)

        # Brief pause between calls
        if i < len(selected):
            time.sleep(3)

    # Report
    reporter = Reporter(results, target_number=args.target)
    reporter.print_summary()

    if args.verbose:
        reporter.print_transcripts()

    if args.output:
        reporter.write_json(args.output)
        print(f"Report written to {args.output}")

    time.sleep(5)
    # Exit code: 1 if any findings, 0 if clean
    return 1 if reporter.findings else 0


if __name__ == "__main__":
    sys.exit(main())