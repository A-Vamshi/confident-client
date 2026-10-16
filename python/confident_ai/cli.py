import argparse
import sys
from typing import List, Optional

from .client import ConfidentAI

GATE_HELP = (
    "Check your project against its governance policy, and exit non-zero if "
    "it doesn't pass. Reads the project API key from CONFIDENT_PROJ_API_KEY. "
    "Your project must belong to a governance policy on Confident AI; if it "
    "doesn't, contact your organization administrator."
)

NO_POLICY_HINT = (
    "Make sure your project belongs to a governance policy. If it doesn't, "
    "please contact your organization administrator."
)


def _report(message: str, quiet: bool, error: bool = False) -> None:
    if not quiet:
        print(message, file=sys.stderr if error else sys.stdout)


def gate(quiet: bool = False) -> int:
    try:
        governance = ConfidentAI().governance
    except ValueError as error:
        _report(str(error), quiet, error=True)
        return 1

    try:
        assessment = governance.assess()
    except Exception as error:
        _report(
            f"Could not assess governance for your project: {error}\n"
            f"{NO_POLICY_HINT}",
            quiet,
            error=True,
        )
        return 1

    policy = assessment.governance_policy.name
    if assessment.passed:
        _report(f"Governance gate passed against {policy}.", quiet)
        return 0

    _report(
        f"Governance gate failed against {policy}. "
        "One or more controls did not pass.",
        quiet,
    )
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="confident-ai",
        description="The Confident AI command line.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    gate_parser = commands.add_parser(
        "gate", help=GATE_HELP, description=GATE_HELP
    )
    gate_parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Print nothing. The exit code still reports the verdict.",
    )

    args = parser.parse_args(argv)
    return gate(quiet=args.quiet)
