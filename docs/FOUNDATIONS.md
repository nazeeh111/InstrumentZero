# InstrumentZero: research foundations and implementation advice

Checked 2026-10-26. This is architecture advice from primary sources, not a replication or an exhaustive novelty review. No credentials, API services or hardware were accessed.

## Findings that change the build

The Nature link is valid: *Designing physics experiments with artificial intelligence*, a Review by Jonathan Klimesch and coauthors, published 2 September 2026, Nature 657, 47–58, DOI 10.1038/s41586-026-10898-6. The accessible abstract frames four problems: search-space representation, reliable fast simulators, computable scientific objectives and mixed discrete/continuous search. Full text is subscription-restricted in this session. Do not present the review as a newly replicated experiment, or claim its inaccessible methods were inspected. [Publisher](https://www.nature.com/articles/s41586-026-10898-6)

**Important version boundary:** Bluesky Adaptive 0.x is discontinued; 0.4.0 is its final release. The current README says 1.0 adopts the blop codebase and drops the prior Kafka/Tiled Agent base, adjudicators, server and lockstep recommenders. Old examples cannot be assumed compatible. For v0.1, expose optional plans against Bluesky itself or defer the adaptive bridge until a version is pinned and exercised. [Current source](https://raw.githubusercontent.com/bluesky/bluesky-adaptive/main/README.md), [docs](https://blueskyproject.io/bluesky-adaptive/).

## Reuse and boundaries

| Foundation | Established capability | Consequence for InstrumentZero |
|---|---|---|
| [Bluesky](https://raw.githubusercontent.com/bluesky/bluesky/main/README.md) | Experiment orchestration, streaming observations and metadata, interruption recovery, pluggable I/O | Optional execution target. Do not rebuild a facility control engine or claim safe arbitrary hardware control. |
| [Phyphox](https://phyphox.org/docs/remote-interface/) | Phone sensor experiments with a local REST interface | Read-only import is a practical first adapter. A real device must be explicitly connected before a live claim. |
| [PyVISA](https://pyvisa.readthedocs.io/en/latest/) | Instrument communication across GPIB/serial/USB/Ethernet using backends | Optional read adapter; no universal command emission, resource scan or instrument actuation. |
| [PyMeasure](https://pymeasure.readthedocs.io/en/latest/) | Instrument classes and queued experiment procedures with GUIs | Reuse a tested driver if a particular supported instrument is added; not a dependency for browser sensor workflows. |
| [BoTorch](https://raw.githubusercontent.com/meta-pytorch/botorch/main/README.md) | Composable probabilistic models, acquisition functions and optimizers on PyTorch | Appropriate later for expensive black-box design. Small analytical forward models are cheaper and easier to audit without its dependency stack. |
| [SciPy](https://docs.scipy.org/doc/scipy/tutorial/optimize.html) | Least squares, numerical optimization and roots | Use existing optimization and signal/statistical methods; preserve model assumptions and explicit units. |

This product's defensible distinction is a constrained compiler joining a question/specification, identifiability, calibration, validated acquisition, inference, adaptive recommendation and an evidence package. These components separately have extensive prior art. No claim of a new general scientific agent or first adaptive-design system follows from this investigation.

### Phyphox contract details

The machine-readable source is [openapi.yaml](https://phyphox.org/docs/remote-interface/openapi.yaml). `GET /get?time=full&accX=full` requests buffers by their actual experiment names; missing requested buffers may be silently skipped, so validate response presence and aligned lengths. `status.session` detects experiment changes. Incremental queries can use the time buffer as reference. `null` values denote nonfinite samples and must be rejected or marked explicitly. Requests should be serialized. Remote access is manually enabled per session and has no authentication; do not auto-discover phones. For local HTTP browser use, HTTPS-to-HTTP mixed content can block requests. Prefer an explicit Python import CLI accepting the user-supplied local endpoint. Do not call `/control`, `/set` or trigger endpoints by default. No device contract was exercised here.

### License checks

[PyVISA](https://raw.githubusercontent.com/pyvisa/pyvisa/main/LICENSE), [PyMeasure](https://raw.githubusercontent.com/pymeasure/pymeasure/master/LICENSE.txt) and [BoTorch](https://github.com/meta-pytorch/botorch/blob/main/LICENSE) use MIT. [SciPy](https://raw.githubusercontent.com/scipy/scipy/main/LICENSE.txt) and [Bluesky Adaptive](https://github.com/bluesky/bluesky-adaptive/blob/main/LICENSE) use BSD-3-Clause. [Phyphox experiments](https://raw.githubusercontent.com/phyphox/phyphox-experiments/master/LICENSE) and the current REST specification use GPL v3. Do not vendor their experiment XML or implementation into an MIT project without retaining applicable terms. Writing a separate client to the public protocol need not copy those sources. This is a provenance inventory, not legal advice. Recheck exact dependency versions before shipping notices.

## Scholarly alternatives and limits

[Deep Adaptive Design](https://arxiv.org/abs/2103.02438), Foster et al., ICML 2021, already learns an amortized policy from experiment history to avoid expensive online design optimization. It uses sequential contrastive information objectives. Therefore “learn a policy selecting the next experiment” is not by itself original. The paper supplies a useful computational baseline and motivation; its reported performance was not reproduced here.

[Robust Experimental Design via Generalised Bayesian Inference](https://arxiv.org/abs/2511.07671), Barlas, Sloman and Kaski, v2 revised 16 October 2026, develops a Gibbs expected-information acquisition and reports robustness to outliers and noise misspecification. This makes stress tests under wrong likelihoods essential rather than optional decoration.

[Representative, Informative, and De-Amplifying: Requirements for Robust Bayesian Active Learning under Model Misspecification](https://arxiv.org/abs/2506.07805), Tang, Sloman and Kaski, v3 31 March 2026, accepted AISTATS 2026, gives R-IDeA acquisition and analyzes error amplification. Search initially returned an older title, so cite the current title/version. It cautions against interpreting informativeness alone as improved physical accuracy.

[Maximin Robust Bayesian Experimental Design](https://arxiv.org/abs/2603.14094), Abdulsamad et al., v2 12 May 2026, formulates robust design as a max-min problem with information-theoretic constraints. It motivates distribution-shift evaluation but is too substantial to claim as an implemented baseline without implementing and validating its estimator.

## An implementable scoped research contribution

Recommendation: evaluate **calibration-aware, cost-aware dual-modality stiffness design** with a compact learned acquisition surrogate, and retain the exact classical method as the default unless measurement proves the surrogate useful. The original contribution can be an openly reproducible empirical study and implementation, not an unsupported algorithmic novelty claim.

Use force F in newtons and displacement y in metres:

`y = b + c F + epsilon`, `c = 1/k`, stiffness `k` in N/m.

An action specifies force, sensor modality, repeat count/exposure and acquisition cost. Sensor context contains externally measurable position noise, scale uncertainty, field of view, allowable force and setup cost. A second (precise, costly) modality can be a calibrated ruler/dial gauge import; video is cheaper. Compare all policies with identical available actions, calibration knowledge, inference and **total cost budget**, including modality switching and setup where modeled. Do not give the learned policy true stiffness, drift values or future observations.

Fit intercept and compliance jointly. For known Gaussian noise, maintain a Gaussian posterior over `(b,c)` and update through standard rank-one linear-regression formulas. Use prior sensitivity checks. For positive compliance well separated from zero, transform posterior quantiles to stiffness by reciprocals in reverse order. If the compliance interval crosses zero, report stiffness as unbounded/unreliable rather than using symmetric `k ± sigma`.

For a candidate h=[1,F] with independent variance R, covariance update is `C_new = C - C h h^T C/(R+h^T C h)`. A target-specific acquisition is reduction in `C[c,c]` per cost; joint Gaussian information gain is `0.5 log(1+h^T C h/R)`. These answer different scientific goals. Include both or explicitly label the implemented one. Repeatedly loading one force cannot identify an unknown intercept and compliance without prior assumptions. A simple domain-specific endpoint design is a necessary strong baseline.

**Calibration is shared uncertainty.** A single pixel-to-metre scale error affects every observation together. It must not shrink like independent sensor noise. Propagate it with a shared nuisance parameter, correlated covariance, or Monte Carlo draws of one scale per complete experiment. The same applies to force scale and sample clock. Fitting an intercept avoids pretending a common zero frame has independent noise in every difference. Calibration drift is a distinct stress condition, not simply larger white noise.

**Learned component:** train a small ridge/MLP surrogate to predict marginal target-variance reduction or a two-step value from posterior summaries, action descriptors and observable sensor context. Keep fixed train/validation/test random seeds and disjoint physical parameter ranges for out-of-distribution tests. Save weights, training configuration and training cost. Run the classical exact formula as reference. If the surrogate merely approximates a cheap closed form, explicitly report that learning adds no practical benefit and retain classical default. A more meaningful later extension is finite-budget lookahead with fixed setup costs, where greedy gain/cost can lose to a policy accounting for future acquisitions.

## Evaluation acceptance criteria

- Baselines: fixed uniform force schedule, random feasible action, exact target-variance or joint-EIG acquisition, and endpoint design (domain-specific). Add cost-blind and calibration-blind ablations. A surrogate should also be compared to its exact teacher, not only weak fixed schedules.
- Record repeated paired trials, preferably 100+ seeds per regime, for nominal noise, heteroscedastic noise, calibration drift and a deliberately misspecified nonlinear spring. Ground truth belongs only to the simulator/scorer.
- Report stiffness relative/RMSE error, 95% interval coverage and width, actual action cost, measurements, target variance/information gain, computation time, training cost and action failures. Aggregate paired differences with confidence intervals. Do not pool all regimes into a headline that hides failures.
- Use fresh observations per repeated action, or common random numbers keyed by trial/action/replicate rather than sharing a single cached observation forever. Give policies equal budgets and do not allow overshoot.
- Exact Gaussian posterior variance does not depend on observed values when noise/design are fixed. Under that restricted model a changing uncertainty-based design can be sequential without actually adapting to observed outcomes. State this limitation. Heteroscedastic or model-discrimination tests are needed for richer adaptivity.
- Real data can validate the estimator and its assumptions; replay cannot validate a counterfactual recommended load that was never recorded. Separate measured, replayed, simulated and merely proposed actions in every UI/export.
- A nominal tuning-fork label is an external reference check, not a traceable calibration. An independently computed FFT on the same waveform checks software, not independent physical truth. Explicitly distinguish these.

## Acoustic second domain

Use damped sinusoid or stationary sinusoid with offset, initialize frequency from SciPy spectral analysis, and fit with SciPy least squares. Detect insufficient duration, Nyquist violations, clipping, weak peak prominence, multiple strong peaks and nonstationarity. A largest FFT peak alone does not distinguish a fundamental from a harmonic. Report sample-clock uncertainty as a shared relative frequency floor. Non-overlapping windows can test repeatability but must not be passed off as independent recordings. An interval conditional on a sinusoid model does not establish that the model is physically correct.

## Presentation capabilities investigated

[PaperVizAgent](https://raw.githubusercontent.com/google-research/papervizagent/main/README.md), formerly PaperBanana, is an Apache-2.0 reference-driven illustration pipeline with model API configuration and image-generation calls. Its source describes demonstration rather than production use. Under this project's no-separately-billed-API constraint, do not provision keys. Use audited local SVG diagrams and charts rendered from actual benchmark outputs. No PaperVizAgent execution was attempted.

[/brag](https://raw.githubusercontent.com/latent-spaces/brag/main/README.md) is a free agent skill for short project launch videos, with an output folder retaining plan/composition/share copy/video. The classic path uses Hyperframes, Node 22+ and FFmpeg; optional narration uses Kokoro. The local installed brag skill can be read later if video is built. Capture genuine working product flows and label replay/simulation. Do not add invented experimental success or synthetic “scientific footage.” No brag execution was attempted during this investigation.
