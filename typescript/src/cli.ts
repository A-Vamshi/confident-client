#!/usr/bin/env node
import { ConfidentAI } from "./client";
import { GovernanceClient } from "./governance/client";

const USAGE = `Usage: confident-ai gate [-q | --quiet]

Check your project against its governance policy, and exit non-zero if it
doesn't pass. Reads the project API key from CONFIDENT_PROJ_API_KEY. Your
project must belong to a governance policy on Confident AI; if it doesn't,
contact your organization administrator.

Options:
  -q, --quiet  Print nothing. The exit code still reports the verdict.
  -h, --help   Show this help.`;

const NO_POLICY_HINT =
  "Make sure your project belongs to a governance policy. If it doesn't, please contact your organization administrator.";

const HELP_FLAGS = ["-h", "--help"];
const QUIET_FLAGS = ["-q", "--quiet"];

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function gate(quiet = false): Promise<number> {
  const report = (message: string, error = false) => {
    if (!quiet) (error ? console.error : console.log)(message);
  };

  let governance: GovernanceClient;
  try {
    governance = new ConfidentAI().governance;
  } catch (error) {
    report(messageOf(error), true);
    return 1;
  }

  try {
    const assessment = await governance.assess();
    const policy = assessment.governancePolicy.name;
    if (assessment.passed) {
      report(`Governance gate passed against ${policy}.`);
      return 0;
    }
    report(
      `Governance gate failed against ${policy}. One or more controls did not pass.`,
    );
    return 1;
  } catch (error) {
    report(
      `Could not assess governance for your project: ${messageOf(error)}\n${NO_POLICY_HINT}`,
      true,
    );
    return 1;
  }
}

export async function main(
  args: string[] = process.argv.slice(2),
): Promise<number> {
  const [command, ...options] = args;
  if (command !== "gate" && HELP_FLAGS.includes(command)) {
    console.log(USAGE);
    return 0;
  }
  if (command !== "gate") {
    console.error(
      command === undefined ? USAGE : `Unknown command: ${command}\n\n${USAGE}`,
    );
    return 2;
  }
  if (options.some((option) => HELP_FLAGS.includes(option))) {
    console.log(USAGE);
    return 0;
  }
  const unknown = options.find((option) => !QUIET_FLAGS.includes(option));
  if (unknown !== undefined) {
    console.error(`Unknown option: ${unknown}\n\n${USAGE}`);
    return 2;
  }
  return gate(options.length > 0);
}

if (require.main === module) {
  void main().then((code) => {
    process.exitCode = code;
  });
}
