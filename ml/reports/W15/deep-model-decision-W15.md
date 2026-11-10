# W15 — deep-model Go/No-Go decision

**Task:** B-W15-06 · **Decision: `NO-GO`.**

A deep model is not justified by being more advanced than XGBoost. It would be
justified only by documented evidence of every prerequisite below. None is met.

## 1. Prerequisite assessment

| Prerequisite | Status | Evidence |
|---|---|---|
| XGBoost demonstrably fails a structured temporal behaviour | **Not shown** | XGBoost reaches AP 1.0000 on the synthetic grouped control; no structured failure is documented |
| Enough independent runs exist | **Not met** | 0 predictive-eligible real runs; 8 synthetic pair groups |
| A concrete incremental scientific question | **Not met** | No question that a sequence model would answer differently under the current evidence |
| Fair, leakage-safe evaluation protocol | **Available for XGBoost only** | W11/W14 grouped protocol is reusable, but no new deep-model protocol or data exists |
| Defensible dataset sufficiency | **Not met** | Correlated telemetry windows are not independent samples |
| Implementation/verification time remains | **Not justified** | W15 canonical effort is 12 h and no incremental question exists |

## 2. Decision rationale

1. The scientific gate is still `NO-GO / FIX DATA` (W12 G3) with 0 predictive-eligible
   real runs. A deep model would be trained on the same synthetic fixture that
   saturates the tree model, adding complexity without answering a scientific
   question.
2. No documented structured temporal failure of XGBoost exists on admissible data.
   Without such a failure, architecture comparison is not a controlled experiment.
3. The available synthetic population has 8 correlated pair groups. Counting
   overlapping telemetry windows as independent samples would violate the project's
   independence invariant.
4. Adding PyTorch/TensorFlow or a training pipeline would expand scope, cost and
   security surface without evidence of incremental value. W15 must not do this.

`NO-GO` means: do not implement a deep-model training pipeline in W15 or W16. It
does not assert that deep models are permanently inappropriate; it asserts that the
present evidence and time budget do not justify one.

## 3. Reopening conditions

A future `GO` requires all of the following, documented in a new decision record:

1. Admissible real grouped development data with enough independent runs.
2. A documented structured temporal behaviour that XGBoost demonstrably misses
   (for example, a sequence-dependent failure reproduced under fair grouped folds).
3. A concrete incremental question and a predeclared, leakage-safe evaluation
   protocol with the same label/horizon discipline.
4. A defensible sample-size argument that does not count correlated windows as
   independent experiments.
5. Available implementation and verification time without displacing the physical
   measurement programme.
6. Explicit approval that the deep model is a research branch, not a release
   candidate.

## 4. Prohibited actions under this decision

- No deep-model implementation or dependency addition.
- No architecture contest on the saturated synthetic fixture.
- No use of the W16 locked test to justify a deep model.
- No claim that `NO-GO` proves XGBoost is the best possible model.

## 5. Binding

- W15 manifest SHA-256: `3f1a16939e1c16345e9948eb109085d123d3e57a57717132b0ab9c2d89d5eafa`
- Related: `A3-report.md`, `prediction-vs-diagnosis-W15.md`, `model-card-W15.md`
- Scientific class: `SYNTHETIC_SOFTWARE_CONTROL_ONLY`
