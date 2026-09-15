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
    JUDGE_PROVIDER,
    CALL_TIMEOUT,
    CALL_IDLE_TIMEOUT,
    GENERATOR_PROVIDER,
    GENERATOR_MODEL,
    SCENARIO_DIR,
)
from scenario_loader import ScenarioLoader
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

  # Recon a target and generate scenarios tailored to it
  python yapper.py --target +15559876543 --generate-scenarios
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

    generate_group = parser.add_argument_group("scenario generation")
    generate_group.add_argument(
        "--generate-scenarios",
        action="store_true",
        help="Place a benign recon call, then write one scenario per OWASP category",
    )
    generate_group.add_argument(
        "--scenario-dir",
        default=SCENARIO_DIR,
        help="Where to write generated scenarios (default: scenarios/)",
    )
    generate_group.add_argument(
        "--force",
        action="store_true",
        help="Overwrite generated scenarios that already exist",
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


def validate_config(use_judge=True, use_generator=False):
    missing = []

    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not TWILIO_PHONE_NUMBER:
        missing.append("TWILIO_PHONE_NUMBER")
    if not WEBHOOK_BASE_URL:
        missing.append("WEBHOOK_BASE_URL")
    # Only the Anthropic judge needs a key. A local OpenAI-compatible server
    # (JUDGE_PROVIDER=local) authenticates with a placeholder, so requiring one
    # here would block a perfectly valid local run.
    if use_judge and JUDGE_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")

    # Recon generates scenarios through the generator, which may sit on a
    # different provider than the judge.
    if use_generator and GENERATOR_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        if "ANTHROPIC_API_KEY" not in missing:
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


def wait_for_call_completion(engine, call_sid, timeout=CALL_TIMEOUT,
                             idle_timeout=CALL_IDLE_TIMEOUT):
    elapsed = 0
    interval = 2

    while elapsed < timeout:
        if engine.is_complete(call_sid):
            return True

        # A talkative agent can hold one gather open for a full minute, so slow
        # progress is normal. Silence for much longer than that is not.
        idle = engine.seconds_since_activity(call_sid)
        if idle is not None and idle > idle_timeout:
            print(f"Warning: no activity on call {call_sid} for {idle:.0f} seconds")
            return False

        time.sleep(interval)
        elapsed += interval

    print(f"Warning: call {call_sid} timed out after {timeout} seconds")
    return False


def run_scenario_generation(engine, args):
    """Place one recon call, then write a scenario per category from what it heard."""
    try:
        import scenario_generator
    except ImportError:
        print("Error: --generate-scenarios requires scenario_generator.py, which is missing.")
        return 1

    print()
    print("  Yapper - Scenario Generation")
    print(f"  Target:    {args.target}")
    print(f"  Generator: {GENERATOR_PROVIDER} ({GENERATOR_MODEL})")
    print(f"  Output:    {args.scenario_dir}")
    print()

    engine.pending_scenario = scenario_generator.recon_scenario()

    print("[1/2] Placing recon call")
    call_sid = initiate_call(
        account_sid=TWILIO_ACCOUNT_SID,
        auth_token=TWILIO_AUTH_TOKEN,
        from_number=TWILIO_PHONE_NUMBER,
        to_number=args.target,
        webhook_base_url=WEBHOOK_BASE_URL,
    )

    completed = wait_for_call_completion(engine, call_sid)
    transcript = engine.get_transcript(call_sid)
    engine.remove_session(call_sid)

    agent_turns = [t for t in transcript if t["role"] == "agent"]
    if not agent_turns:
        print("  Recon call captured nothing from the agent, cannot generate scenarios.")
        return 1

    print(f"  Captured {len(agent_turns)} agent response(s)"
          f"{'' if completed else ' (partial, call did not finish)'}")

    if args.verbose:
        for entry in transcript:
            role = "AGENT" if entry["role"] == "agent" else "USER"
            print(f"     [{role}] {entry['content']}")
        print()

    print("[2/2] Generating scenarios")

    def progress(owasp_id, category):
        print(f"  {owasp_id} ...", flush=True)

    written, skipped, failed, checks = scenario_generator.generate_all(
        transcript,
        output_dir=args.scenario_dir,
        force=args.force,
        on_progress=progress,
    )

    print()
    for path in written:
        print(f"  wrote   {path}")
        for level, message in checks.get(path, []):
            print(f"          {level:<5} {message}")
    for name, path in skipped:
        print(f"  exists  {path} (use --force to overwrite)")
    for owasp_id, error in failed:
        print(f"  failed  {owasp_id}: {error}")

    print()
    print(f"  {len(written)} scenario(s) written, {len(skipped)} skipped, "
          f"{len(failed)} failed.")
    warnings = sum(1 for f in checks.values() for level, _ in f if level == "warn")
    if warnings:
        print(f"  {warnings} check warning(s) above.")
    if written:
        print("  Review them before running a scan.")
        print()

    return 0 if written else 1


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

    # Scenario generation is its own mode: one benign recon call, then files.
    if args.generate_scenarios:
        validate_config(use_judge=False, use_generator=True)

        webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
        webhook_thread.start()
        time.sleep(2)

        from webhook import engine
        return run_scenario_generation(engine, args)

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
    judge_status = f"enabled ({JUDGE_PROVIDER})" if use_judge else "disabled"
    print(f"  Judge:     {judge_status}")
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

        # Wait for the call to finish. A call that ran out of time still spoke to
        # the target, so whatever was captured gets analyzed rather than thrown
        # away; the result is flagged so a partial run is never mistaken for a
        # clean one.
        completed = wait_for_call_completion(engine, call_sid)
        transcript = engine.get_transcript(call_sid)

        if not transcript:
            print(f"  No transcript captured, skipping analysis")
            engine.remove_session(call_sid)
            continue

        result = analyzer.analyze(scenario, transcript)
        result["completed"] = completed
        results.append(result)

        status = "FINDING" if result["triggered"] else "PASS"
        if not completed:
            status += " (partial transcript)"
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