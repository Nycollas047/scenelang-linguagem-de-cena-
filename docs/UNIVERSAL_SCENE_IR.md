# Universal Scene IR (experimental, schema 1.0.0)

The Universal Scene IR is a destination-neutral, serializable scene model. It is
an additive API: existing SceneLang YAML remains the authoring format and its
syntax and compilation targets are unchanged. Convert a validated `Scene` with
`scene.to_universal_ir()` and serialize with `ir.to_dict()`.

The published JSON Schema is
[`schemas/universal-scene-ir-1.0.0.schema.json`](../schemas/universal-scene-ir-1.0.0.schema.json).
The version is carried by every document. Incompatible changes require a new
major schema version.

## Core fields

- `entities`: stable ids, semantic kind, labels/descriptions, and extensible properties.
- `coordinate_system`: dimensionality, units, handedness, up axis, and origin.
- `geometry`: typed geometry records linked to entity ids; v1 maps SceneLang boxes to normalized `box2` records.
- `relations`: semantic or spatial relations between entities.
- `materials`, `lighting`, and `camera`: destination-neutral scene properties.
- `temporal`: duration, timebase, and animation data reserved for animated scenes.
- `constraints`: source-tagged constraints, retaining SceneLang assertions and image checks.
- `metadata`: provenance and source information.

## Adapter contract

An adapter exposes a stable `name`, `capabilities() -> set[str]`, and
`export(scene)`. `adapter_report(scene, adapter)` compares declared capabilities
with IR feature groups and returns supported groups, unsupported groups, and an
explicit loss entry for each unsupported group. Adapters must not imply that an
unsupported property was preserved.

The current release defines the contract and reporting interface; it does not
ship Blender, game-engine, video, or renderer adapters. The v1 SceneLang
projection is primarily 2D. Three-dimensional geometry, full temporal data,
typed material graphs, and renderer-specific light/camera models remain future
work; source fields that cannot be projected are retained in `metadata` where
possible.

Validation is available as `validate_ir(value)` and returns stable path/message
diagnostics. The schema version and unique entity ids are mandatory, and all
geometry must reference a declared entity.
