# Supervised physical acceptance still required

The current release processes authentic external observations and checks held-out reference measurements. It does not establish actual-device camera/microphone acceptance or an independently calibrated webcam stiffness result. This checklist specifies the missing evidence; unchecked items are not completed experiments.

## Camera stiffness workflow

1. A human chooses a secure low-force spring/cantilever arrangement, limits extension/force to a known elastic range, and prevents falling masses. Use a fixed camera, a dark fiducial and a length reference in the same motion plane. No software load actuation is supported.
2. Retain setup photographs/video, specimen identity, instrument identity, date, known masses/forces, gravitational-acceleration assumption, length-reference calibration and uncertainties. Do not substitute example calibration defaults.
3. Deliberately grant camera access; test Stop and permission denial. Select the fiducial and inspect pixel positions at rest. Move a known distance to verify sign/scale. Test lost-marker recovery. Retain original recordings separately because the Lab captures positions only.
4. Collect repeated settled measurements at several distinct forces, including loading/unloading and low-force controls. Inspect residuals, curvature, hysteresis and position uncertainty. A good fit alone does not establish physical accuracy.
5. Execute one feasible recommended observation manually. Record its actual force, time, calibration and outcome as a new observation, not a simulated counterfactual. Compare the updated interval and model diagnostics.
6. Compare with a separately characterized stiffness reference on the same specimen, retaining its method, uncertainty and independence. A second regression of the same data is a numerical cross-check only. A dynamic oscillation method is an option only with justified effective mass, damping and clock calibration; a nominal material modulus is insufficient.
7. Export and reproduce the package from another directory. Report disagreement and uncertainty limitations even if the desired target was missed.

## Microphone workflow

Use a characterized acoustic source with a documented frequency and clock reference. Deliberately enable/capture/stop the microphone, check permission denial and cancellation, and retain the original audio. Test clipping and background/competing tones. Repeat recordings and compare with the independent source reference. Record browser resampling and microphone processing. A tuning-fork stamp or agreement between two FFT implementations does not by itself establish traceable accuracy.

## Acceptance record

Record observed behavior for each device/browser, measured result, reference, interval interpretation, limitations and exported source hash. The public fixture can be contributed under an explicit redistribution license. Actual physical setup and supervision cannot be replaced by automatic code execution.
