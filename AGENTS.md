# Research software maintenance rules

- Read README.md, provenance/source-versions.json, examples/cases.json and examples/segmentation.json before changing execution paths.
- Preserve recorded research files in research/ and archive/ byte-for-byte. A method change requires an explicit plan, version record, prediction and falsification criterion. Do not silently update expected hashes to bless changed results.
- Distinguish the supported point-normal CSV pipeline from unexecuted STL/Blender sampling and historical csproj snapshots. Do not infer real-scan validation, general CAD solid output or accuracy from output hashes.
- Write generated outputs to a fresh runs/ directory. Never overwrite inputs or references. Use explicit UTF-8 for Chinese text files.
- Run checks appropriate to the change. For execution/environment changes, check source/input hashes and affected outputs. Record actual failures instead of weakening comparison criteria.
- After reviewed changes, run tools/seal-release.mjs and tools/verify-package.mjs. The seal tool must reject changed recorded research sources.
- The thesis PDF is a reading snapshot with separate copyright and version notes. Do not edit the original thesis, remove formulas or silently rewrite content as a packaging task.
