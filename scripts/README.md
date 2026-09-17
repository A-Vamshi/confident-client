# SDK generation

The Python and TypeScript SDKs are generated from the OpenAPI spec
confident-cloud publishes. Nothing under `python/confidentai/` or
`typescript/src/` that carries an `@generated` banner is edited by hand — change
the route upstream, regenerate, and both SDKs move together.

## Running it

From `python/`:

```bash
poetry run python ../scripts/generate_sdk.py            # write
poetry run python ../scripts/generate_sdk.py --check    # verify, no writes (CI)
```

`--spec-dir` points at another checkout of confident-cloud, and
`--descriptive false` drops docstrings, JSDoc and explanatory comments. A run
classifies every file before writing any of it, so it refuses rather than
overwriting something hand-written.

## The two files you touch

**`generate_sdk.py`** is the entrypoint and the only file you run. It reads the
spec once, hands it to each renderer, and writes what comes back.

**`stateful_resources.yml`** declares the stateful handles — the objects like
`client.dataset(id)` that hold a record's id so callers stop passing it to every
call. Its header is a menu of every key it accepts; a resource absent from it
still gets a normal stateless client.

## `sdkgen/`

Everything else. The three renderers sit at the top, one per kind of artifact:

| | |
| --- | --- |
| `types.py` | the wire types — one module per resource |
| `clients.py` | the endpoint enum, the operations, and the clients that compose them |
| `stateful_clients.py` | the handles `stateful_resources.yml` describes |
| `constants.py` | everything the generator is told, as data |

`core/` is what those stand on: `spec.py` reads the OpenAPI document,
`operations.py` models one operation, `shapes.py` turns a schema into a type,
`naming.py` turns spec names into code names, `output.py` writes and formats,
`errors.py` holds the one exception.

## Two conventions worth keeping

**Each renderer sits beside its twin in the other language** — `render_client`
next to `render_typescript_client`. It is the only thing that makes a difference
between the two SDKs visible in review.

**A pure refactor must leave the output byte-identical.** Run `--check` after
any change that was not meant to alter what is generated; it should report the
file count unchanged.