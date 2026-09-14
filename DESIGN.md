# MarketLab Design Index

MarketLab's design is split into concise documents:

- [ALGORITHM_DESIGN.md](./ALGORITHM_DESIGN.md) covers research intent, market-regime theory,
  single-name opportunity theory, outcome validation, and current model proposals.
- [IMPLEMENTATION_DESIGN.md](./IMPLEMENTATION_DESIGN.md) covers the local application
  architecture, CLI surfaces, data layout, source handling, snapshot semantics, and
  implementation constraints.
- [VERSIONS.md](./VERSIONS.md) records current pillar versions and bump rules.

The split is intentional. Algorithm design should explain what the research system is trying to
learn. Implementation design should explain how the current local tool records data and runs that
research without turning every modeling idea into permanent infrastructure. Version tracking stays
separate so bump decisions remain visible.

For day-to-day command usage, start with [README.md](./README.md). For indicator definitions,
start with [KNOWLEDGE.md](./KNOWLEDGE.md).
