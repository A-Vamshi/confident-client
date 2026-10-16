# Confident AI SDKs

Official SDKs for the [Confident AI](https://www.confident-ai.com) API —
**275 operations across 35 resources**, covering platform administration
(organizations, projects, API keys, members, roles, policies, governance) and
the data plane (prompts, datasets, traces, spans, threads, metrics, test runs,
evaluations, red teaming, dashboards and more).

| Language | Package | Location |
| --- | --- | --- |
| Python | `confident-ai` | [`python/`](./python) |
| TypeScript | `confident-ai` | [`typescript/`](./typescript) |

> **Both SDKs are generated** from the OpenAPI spec confident-cloud publishes.
> Nothing under `python/confident_ai/` or `typescript/src/` carrying an
> `@generated` banner is edited by hand — change the route upstream and
> regenerate. See [`scripts/README.md`](./scripts/README.md).

> Running evaluations in your test suite, or instrumenting an app with tracing,
> is [`deepeval`](https://github.com/confident-ai/deepeval) and 
> [`confident-trace`](https://github.com/confident-ai/confident-trace)'s job. 
> These SDKs are the API: they manage the resources your evals and traces refer to, 
> and read the results back.

## Design

Both SDKs share one surface. Every resource has a client whose methods are the
routes it owns, named for what they do rather than for the operation id:

```python
# Python
from confident_ai import ConfidentAI

client = ConfidentAI(api_key="confident_us_org_...")

organization = client.organization.get()          # -> Organization
projects = client.projects.list()                 # -> ProjectList
datasets = client.datasets.list()                 # -> DatasetList
```

```ts
// TypeScript
import { ConfidentAI } from "confident-ai";

const client = new ConfidentAI({ apiKey: "confident_us_org_..." });

const organization = await client.organization.get();  // -> Organization
const projects = await client.projects.list();         // -> ProjectList
const datasets = await client.datasets.list();         // -> DatasetList
```

### Stateful handles

Three resources also have a handle that holds a record's id, so its methods
stop asking for what the object already knows:

```python
project = client.project("<PROJECT-ID>").get()   # fills the handle, returns it
project.name = "Checkout Assistant"
project.update()                                  # sends what the handle holds
project.list_members()

prompt = client.prompt("<PROMPT-ID>")
prompt.pull(label="production")                   # cached, refreshed in the background
prompt.interpolate(name="Joe")

dataset = client.dataset("<DATASET-ID>").pull()
dataset.goldens[0].input = "What is the capital of Peru?"
dataset.push()                                    # upserts: ids update, new ones are created
```

`prompt.pull()` keeps the pulled commit on disk and re-pulls it every 60
seconds, so editing a prompt on Confident AI reaches a running process without
a deploy. Pass `refresh=0` to turn both off while you are still editing it.

### Images

`Media` puts an image into any text field of a golden, test case or annotation.
Formatting it into a string leaves a `[CONFIDENT:IMAGE:…]` marker where the
image belongs, and the request carries the image with it:

```python
from confident_ai import Media
from confident_ai.datasets import PushSingleTurnGolden

photo = Media.from_file("cat.png")
golden = PushSingleTurnGolden(input=f"What is in this photo? {photo}")
client.datasets.push(alias="photos", goldens=[golden])
```

```ts
import { Media } from "confident-ai";

const photo = Media.fromFile("cat.png");
await client.datasets.push("photos", [
  { input: `What is in this photo? ${photo}` },
]);
```

`from_url` sends the link. `from_file`, `from_bytes` and `from_base64` send the
image itself, which stays in memory until the process exits. Only images are
supported for now.

Text you pull back carries its images as markers too. `parse_multimodal`
(`parseMultimodal`) turns it into text and `Media` in order, ready to hand to a
model:

```python
from confident_ai import parse_multimodal

parse_multimodal(golden.input)   # ["What is in this photo? ", Media(...)]
```

### Async

Every method has an `a_`-prefixed twin in Python; in TypeScript everything is
already a promise.

```python
organization = await client.organization.a_get()
```

## Authentication

Two kinds of key, because the API has two scopes:

| Key | Environment variable | Reaches |
| --- | --- | --- |
| Organization | `CONFIDENT_ORG_API_KEY` | `organization`, `projects` |
| Project | `CONFIDENT_PROJ_API_KEY` | every other resource |

Either can be passed explicitly as `api_key` / `project_api_key` (`apiKey` /
`projectApiKey`), and one client can hold both. Neither is `CONFIDENT_API_KEY`,
which `deepeval` already uses.

The base URL resolves from `CONFIDENT_BASE_URL`, else `CONFIDENT_REGION`
(`US` / `EU`), defaulting to `https://api.confident-ai.com`.

## Command line

Both packages install a `confident-ai` command. `confident-ai gate` checks the
project against its governance policy and exits non-zero when it doesn't pass,
so a CI step can stop a deployment:

```bash
confident-ai gate        # pip install confident-ai
npx confident-ai gate    # npm install confident-ai
```

It reads `CONFIDENT_PROJ_API_KEY`, and the project must belong to a governance
policy. It exits `0` when the policy passes, `1` when it fails or can't be
assessed, and `2` on bad usage. `-q` / `--quiet` prints nothing and leaves the
verdict to the exit code.

## Conventions

* **Python** mirrors [`deepeval`](https://github.com/confident-ai/deepeval):
  Poetry, `requests`, Pydantic v2, the `CONFIDENT_API_KEY` header, the
  `{ success, data }` response envelope, and pytest.
* **TypeScript** mirrors `deepeval.ts`: `tsc` build, `axios`, interface-based
  types, and Jest with `jest.mock("axios")`.

## Development

```bash
# Python
cd python && poetry install && poetry run pytest

# TypeScript
cd typescript && npm install && npm test && npm run build
```

Regenerating both SDKs from the spec, run from `python/`:

```bash
poetry run python ../scripts/generate_sdk.py            # write
poetry run python ../scripts/generate_sdk.py --check    # verify, no writes
```

A scheduled [workflow](./.github/workflows/openapi-sdk-sync.yml) does the same
daily and opens a PR when the spec has moved.
