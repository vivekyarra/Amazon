# Physical contract schema

TypeScript read models are exported by `index.ts`. The normative service schemas are generated from the Pydantic models in `done_irl/models.py` and checked on every database save. Schema validation is structural; the deterministic verifier additionally enforces acceptable evidence kinds, contract ownership and terminal-state rules, so schema-valid model output alone can never complete a contract.

MIT licensed with the main repository.
