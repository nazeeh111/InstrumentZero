DATA FOR: Development of a novel nickel-based metal force microsensor using bottom-up approach
==============================================================================================

Dataset authors : Wojciech J. Dera, Hanna Konopacka, Dariusz M. Jarząbek
Institution     : Institute of Fundamental Technological Research, Polish Academy of Sciences (IPPT PAN),
                  Pawińskiego 5B, 02-106 Warsaw, Poland
Contact         : Wojciech J. Dera, wdera@ippt.pan.pl
Licence         : CC BY 4.0

Related article
  W.J. Dera, H. Konopacka, D.M. Jarząbek, "Development of a novel nickel-based metal force microsensor using
  bottom-up approach", Precision Engineering 95 (2025) 251-261.
  https://doi.org/10.1016/j.precisioneng.2025.05.003  (open access, CC BY 4.0)

Funding
  National Science Centre, Poland - grant no. 2021/41/N/ST5/02920
  National Centre for Research and Development, Poland - grant no. TANGO-IV-B/0002/2019


1. WHAT IS IN THE DATASET
-------------------------
The measurement data behind the quantitative results of the article (Figs. 7, 8 and 9, Eqs. 7 and 8),
the screen capture shown in Fig. 11, original optical-microscope photographs of the rib deflection shown
in Fig. 12, and the image files of all twelve figures as published. Sensor fabrication and the test set-up
are described in Sections 2.1-2.5 of the article.


2. INSTRUMENTS (Sections 2.3 and 2.5 of the article)
----------------------------------------------------
Force        Calibrated reference force transducer Megatron Elektronik KM1403 (100 N range, 2.0357 mV/V)
             read by a strain-gauge amplifier; logged by the amplifier software.
Capacitance  AD7746 capacitance-to-digital converter, differential mode, chopping off, conversion time
             109.6 ms, CAPDAC B enabled (0x0F, about 1.992 pF), voltage/temperature channel disabled;
             logged by the converter evaluation software as 24-bit hexadecimal codes.
             Codes are converted to capacitance with Eq. 5 of the article:
                 C [pF] = (Code - 0x800000) / 0x800000 * 4.096
Displacement Thorlabs Z825B motorised actuator; during the force-capacitance calibration (Fig. 7)
             the reference transducer was moved at 0.01 mm/s.


3. FILE FORMATS
---------------
*.csv written for this dataset  UTF-8, comma-separated, decimal point, one header row
                                (quantity_unit). Numbers are given with the precision of the source files.
raw/*.csv (force logger)        original exports: semicolon-separated, decimal comma, columns
                                Date; Time (h:m:s:ms, milliseconds not zero-padded, e.g. 20:12:36:30 =
                                20:12:36.030); No. (sample number); Canal 1 (force, N).
*_raw_codes.txt (AD7746)        original exports: tab-separated; column 1 = capacitance code (hex),
                                column 2 = voltage/temperature channel (disabled, 000000).
Images                          PNG / JPG.


4. FOLDERS AND FILES
--------------------
Fig07_force_capacitance_calibration   (Section 3.1, Fig. 7, Eq. 7; measured 6 November 2024)
  raw/force_reference_raw.csv         reference force, 596 samples, mean interval 114.2 ms (68 s)
  raw/capacitance_AD7746_raw_codes.txt  capacitance codes, 459 samples, with the converter set-up header
  The capacitance export contains no timestamps. Each processing step is saved as a separate file:
  processed/step1_paired_raw.csv      the 459 capacitance values (Eq. 5) paired sample by sample with the
                                      first 459 force samples; time = force time stamp in seconds of the day
  processed/step2_time_zeroed.csv     time shifted to start at 0 s
  processed/step3_tared.csv           force tared: F - F(0); capacitance tared as the absolute value |C - C(0)|
                                      (in this differential configuration the capacitance decreases under load)
  processed/step4_time_aligned.csv    force time shifted by -4.999 s; separate capacitance time axis
                                      t_C = 1.326417 * t + 1.2017 s, set so that the onset, plateau and
                                      release of the load coincide in both records
  processed/step5_capacitance_resampled.csv   capacitance linearly interpolated from t_C onto the force time stamps
  processed/step6_tared_resampled_Fig7a.csv   capacitance tared again: C - C(first sample)            -> Fig. 7a
  processed/step7_capacitance_moving_average_Fig7b.csv
                                      capacitance averaged over 5 consecutive samples (trailing window; called
                                      "cumulative moving average" in the article); force not averaged.
                                      Fig. 7b shows the same 5-sample average applied to both signals.   -> Fig. 7b
  processed/step8_moving_average_trimmed_Fig7c.csv
                                      step 6 trimmed to 0-44.9 s (394 samples), both signals averaged over 5
                                      consecutive samples (fewer at the start of the window)             -> Fig. 7c
  processed/step9_linear_fit_Fig7d.csv
                                      force versus capacitance from step 8 with the least-squares line    -> Fig. 7d, Eq. 7

Fig08a_spring_constant   (Section 3.2, Fig. 8a, Eq. 8)
  force_displacement.csv              15 points: loading (8) and unloading (7);
                                      stage_position_mm = actuator reading; displacement_mm = 24.38738 - stage_position_mm
                                      (positive towards the sensor); both branches are used in the fit

Fig08b_capacitance_drift_2N   (Section 3.3, Fig. 8b)
  capacitance_2N_raw_codes.txt        5000 capacitance codes under a constant load of about 2 N (not tared)
  capacitance_drift_2N.csv            sample_no; time_s = sample_no * 0.1096 s (conversion time); capacitance_pF

Fig09_reference_sensor_stability   (Section 3.4, Fig. 9; measured 22 January 2025)
  raw/reference_force_1N_raw.csv      reference transducer loaded vertically with a weight of about 1 N, 513 samples
  raw/reference_force_2N_raw.csv      the same with about 2 N, 608 samples
                                      (logged about once per second; the amplifier samples at 10 Hz with a 5-sample
                                      averaging filter)
  reference_force_1N_2N.csv           the first 513 samples of both records, as plotted in Fig. 9;
                                      time_1N_s and time_2N_s = elapsed time from the logger time stamps

Fig11_capacitance_anomaly   (Section 4.2, Fig. 11)
  Fig11_screen_capture_AD7746_software.png   screen capture of the live plot of the converter evaluation software
                                      (x-axis: sample number). The underlying time series was not exported.

Fig12_rib_deflection_microscope   (Section 4.2, Fig. 12)
  rib_deflection_above_3N_view1.jpg, rib_deflection_above_3N_view2.jpg
                                      optical-microscope photographs of the out-of-plane deflection of the central
                                      ribs above about 3 N

Figures_as_published
  Image files of Figs. 1-12 of the article.


5. FILE LIST
------------
  Fig07_force_capacitance_calibration/processed/step1_paired_raw.csv                             13 070 B
  Fig07_force_capacitance_calibration/processed/step2_time_zeroed.csv                            11 609 B
  Fig07_force_capacitance_calibration/processed/step3_tared.csv                                  11 090 B
  Fig07_force_capacitance_calibration/processed/step4_time_aligned.csv                           16 925 B
  Fig07_force_capacitance_calibration/processed/step5_capacitance_resampled.csv                  11 087 B
  Fig07_force_capacitance_calibration/processed/step6_tared_resampled_Fig7a.csv                  11 081 B
  Fig07_force_capacitance_calibration/processed/step7_capacitance_moving_average_Fig7b.csv       11 061 B
  Fig07_force_capacitance_calibration/processed/step8_moving_average_trimmed_Fig7c.csv           10 005 B
  Fig07_force_capacitance_calibration/processed/step9_linear_fit_Fig7d.csv                       12 066 B
  Fig07_force_capacitance_calibration/raw/capacitance_AD7746_raw_codes.txt                        7 130 B
  Fig07_force_capacitance_calibration/raw/force_reference_raw.csv                                20 867 B
  Fig08a_spring_constant/force_displacement.csv                                                     551 B
  Fig08b_capacitance_drift_2N/capacitance_2N_raw_codes.txt                                       75 034 B
  Fig08b_capacitance_drift_2N/capacitance_drift_2N.csv                                          151 693 B
  Fig09_reference_sensor_stability/raw/reference_force_1N_raw.csv                                18 118 B
  Fig09_reference_sensor_stability/raw/reference_force_2N_raw.csv                                21 584 B
  Fig09_reference_sensor_stability/reference_force_1N_2N.csv                                     16 979 B
  Fig11_capacitance_anomaly/Fig11_screen_capture_AD7746_software.png                              6 658 B
  Fig12_rib_deflection_microscope/rib_deflection_above_3N_view1.jpg                             273 213 B
  Fig12_rib_deflection_microscope/rib_deflection_above_3N_view2.jpg                             533 706 B
  Figures_as_published/Fig01_fabrication_process_scheme.png                                      94 189 B
  Figures_as_published/Fig02_fabrication_steps.png                                            1 254 078 B
  Figures_as_published/Fig03_sensor_on_PCB.png                                                1 007 962 B
  Figures_as_published/Fig04_optical_microscopy.png                                           8 390 151 B
  Figures_as_published/Fig05_experimental_setup.png                                             710 052 B
  Figures_as_published/Fig06_comb_topology.png                                                   80 942 B
  Figures_as_published/Fig07_force_capacitance.jpg                                            1 052 482 B
  Figures_as_published/Fig08_spring_constant_and_drift.png                                      972 685 B
  Figures_as_published/Fig09_reference_sensor_stability.jpg                                   2 617 580 B
  Figures_as_published/Fig10_surface_defects.png                                              7 203 297 B
  Figures_as_published/Fig11_capacitance_anomaly.png                                            137 428 B
  Figures_as_published/Fig12_rib_deflection.jpg                                                 123 887 B
