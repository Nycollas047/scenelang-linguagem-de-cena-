# Data: what scenelang records, and what it can (and cannot) support

scenelang turns an image request into a **declared, checkable specification**. Every time a generated image is
measured against it, the result is a structured record. This document says exactly what is recorded, how to export it,
what it could be used for, and what has **not** been shown.

## What is recorded

One record per measured round (`scenelang project round` → `scenelang project export`), as JSON Lines
(format `scenelang.dataset/1`). A record is self-contained:

| Field | Meaning |
|---|---|
| `cena_yaml`, `cena_hash` | The exact scene that was measured, and its canonical SHA-256 (`canon-v1-sha256`: ignores comments, key order and formatting). |
| `prompt`, `prompt_origem` | The prompt that was actually given to the generator. `informado` = you passed `--prompt-file`; `compilado_da_cena_assumido` = the compiled prompt, **assumed** (not confirmed) to be the one used. |
| `gerador` | Generator name/version, if you passed `--generator`. Otherwise `null`: the record has no provenance on that point. |
| `imagem` | Path inside the project, SHA-256 and size. The image itself is not embedded in the JSONL. |
| `anotacao` | Where the entity boxes came from. `informadas` = someone looked at the image and wrote them (possibly knowing the scene); `anotacao_independente` = derived from an annotation written *without* the scene (`anotador`, `cego` as declared by the annotator; the tool cannot verify blindness). Never a detector. |
| `reconciliacao` | Only with `--annotations`: matched pairs with match scores (audit them), asserts re-evaluated on the annotated boxes, `count(...)` measured from the annotation, `extras` (objects in the image that the scene does not declare) and `ausentes` (declared entities nobody annotated). |
| `braco`, `seed` | Test arm (`--arm`) and generator seed (`--seed`), when given. Repetitions of one arm are what make a pass rate meaningful. |
| `medicoes[]` | One entry per checked constraint: `check` (e.g. `left_of(knight, boss)`), `ok`, `detail`, `source`, `confidence`, `classe`. |
| `nao_medidos` | Constraints and entities that could **not** be measured, with the reason. Absence of a failure is not recorded as a pass. |
| `correcoes`, `prompt_seguinte` | What the correction engine proposed after the failures, and the next-round prompt. |

A sample (3 records, one scene, three prompt variants, boxes estimated by the author) is in
[`examples/dataset/sample.jsonl`](../examples/dataset/sample.jsonl). It demonstrates the **format**, not a result.

```
scenelang project init work --name demo
scenelang project add work boss_arena
scenelang project round work boss_arena image.png --boxes boxes.json --label arm_b \
    --prompt-file prompt_used.txt --generator "name-and-version"
scenelang project export work --out data.jsonl
```

### Independent measurement and repetitions

Boxes written by someone who knows the scene mix measurement and expectation, and a tool that only measures declared
entities cannot see what the model *added*. So:

```
scenelang annotate-form image.png > form.txt          # neutral instructions: give these to the annotator, NOT the scene
# annotator returns scenelang.anotacao/1 JSON: free names + boxes of everything visible
scenelang reconcile scene.yaml annotation.json        # matches names to entities, re-checks asserts, lists extras
scenelang project round work boss_arena image.png --annotations annotation.json --arm B --seed 3 \
    --prompt-file prompt_used.txt --generator "name-and-version"
scenelang project report work boss_arena              # per constraint and arm: passed k of n, Wilson 95% interval
```

Limits, stated plainly: name matching is a heuristic (shared word stems, geometry as a tie-break), so the match table is
meant to be read; `cego` is the annotator's own declaration; a single round per arm shows no variation, and `report`
flags `n < 5` as "do not conclude". An annotator that is another model brings its own errors.

## What this data could be used for (hypotheses)

1. **Evaluating image generators on spatial and structural constraints.** Each constraint is an independent pass/fail
   with provenance, so two generators (or two prompt styles) can be compared constraint by constraint.
2. **Failure → correction pairs for models that write prompts or scenes.** `prompt` + failed `medicoes` + `correcoes` +
   `prompt_seguinte` is a supervised example of "what to change after this failure".
3. **Constraint labels for training or reward-modeling image models.** (`cena_yaml`, `imagem`) with per-constraint
   labels is a structured signal that free-text prompts do not give.

These are **hypotheses about usefulness**. No model has been trained or fine-tuned on this data, and we have not
measured that it improves anything.

## What has and has not been shown

Shown (small, informal, author-run):
- The pipeline produces these records end to end, and the records are reproducible from the files on disk.
- On a Minecraft dungeon scene (3 images per arm, visual comparison), prompts compiled from the scene, with a
  composition guide, produced no invented UI panels (0/3) versus a hand-written prompt (3/3), and placed keys in the
  declared rooms (3/3). The hand-written baseline was written by the same author and did not mention those items.
- On a dark-fantasy boss scene (1 image per arm), the compiled prompts reproduced per-entity details the hand-written
  prompt summarised away (moss on one pillar, chains on the other). The composition guide gave no clear extra benefit
  there.

**Not** shown:
- Any statistical result. Sample sizes are 1–3 images per condition, on two scenes, and the generator was not recorded in those runs.
- That boxes are accurate: in these runs they were estimated by the author and are not independent of the author's
  judgement. Independent annotation, or detector-based measurement, is needed before using the labels for training.
- That training on this data helps a model. That requires an experiment this repository does not contain.

## Before you use it for anything serious

- Record `--generator` and `--prompt-file` every time; without them provenance is missing.
- Have someone other than the scene's author write the boxes, and keep several images per condition.
- Check the terms of the generator that produced the images before redistributing them. The export carries hashes and
  paths, not the pixels.
- Treat `nao_medidos` as unknown, never as passed.
