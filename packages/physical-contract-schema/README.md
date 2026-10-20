# Physical contract schema

TypeScript read models are exported by `index.ts`. Normative service schemas are generated from the Pydantic models in `done_irl/models.py` and checked on every database save. Contract schema validation is structural; the deterministic verifier additionally enforces acceptable evidence kinds, contract ownership and terminal-state rules. Schema-valid LLM output alone cannot complete a contract.

The package is MIT licensed with the main repository. It has not been published as a separate project or accepted as an external contribution; no Open Source mini-challenge eligibility is claimed.
