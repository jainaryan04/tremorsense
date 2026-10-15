# What is new in TremorSense

This summarises the inventive steps and how they differ from the closest published work and patents. The invention disclosure (IDF) uses the same content.

## Closest prior art

| # | Work | What it does | What it does not do |
|---|---|---|---|
| 1 | Powers et al., *Sci. Transl. Med.* 2021 (Apple Watch Motor Fluctuations Monitor, MM4PD) | Continuous tremor and dyskinesia monitoring on a smartwatch, validated against MDS-UPDRS | No intervention. False positives reported while playing instruments, cycling or riding a bus. No uncertainty guarantee. |
| 2 | Kuosmanen et al., *JMIR mHealth uHealth* 8(11):e21543, 2020, doi:10.2196/21543 | Smartphone accelerometer tremor intensity, before vs after medication | Spot measurements only. No severity bands from displacement, no feedback, no forecasting. |
| 3 | US10561839B2, Cala Health, "Systems for peripheral nerve stimulation" | Wrist device with electrical nerve stimulation that can be timed out of phase with tremor | Needs dedicated electrode hardware. No statistical safety gate, no medication modelling. |
| 4 | Tabacof et al., *Front. Hum. Neurosci.* 15:712621, 2021, doi:10.3389/fnhum.2021.712621 | Wearable vibrotactile stimulation for Parkinson's disease, safety study | Fixed stimulation patterns, not driven by tremor phase or severity. |
| 5 | Victorino et al., *Appl. Sci.* 11(16):7354, 2021, doi:10.3390/app11167354 | Predicts wearing-off from fitness-tracker data and questionnaires | Black-box classifier on 2 people. No pharmacokinetic model, no tremor grading. |
| 6 | Arasteh et al., *J. Pers. Med.* 13(2):265, 2023, doi:10.3390/jpm13020265 | Detects medication OFF episodes from multimodal wearable signals | Detection after the fact, not a forecast. No PK/PD model. |
| 7 | Parkinson's KinetiGraph (Global Kinetics), see NICE DG51 | Wrist logger that scores tremor and bradykinesia, with dose reminders at prescribed times | Reminders follow the prescription, not the patient's measured response. No intervention. |
| 8 | Diaz-Rincon et al., arXiv:2508.10284, 2025 | Conformal prediction intervals for Parkinson's medication dose changes from health records | Not sensors, not real-time, not a safety gate for actuation. |
| 9 | Riviere, Rader & Thakor, *IEEE TBME* 45(7):839-846, 1998 (WFLC) | Adaptive Fourier estimation of tremor frequency and phase for surgical tools | A building block TremorSense uses, not a wearable cueing system. |

## Inventive steps

1. **Dual conformal safety gate for a haptic actuator.** Split-conformal prediction sets for activity and for the ordinal UPDRS grade. A cue may fire only when the activity set is exactly {still} and the severity set is at most two adjacent grades. The cue intensity is the set's lower bound. With calibration at α, P(cue intensity > true grade) ≤ α. A softmax-threshold gate gives no such guarantee.
2. **Physics-derived severity on commodity sensors.** Peak-to-peak hand displacement is computed from the orientation-invariant acceleration spectrum (a / (2πf)²). The result maps onto the MDS-UPDRS 3.17 amplitude bands, with a placement flag (in hand vs on wrist) to correct for lever-arm attenuation.
3. **Phase-locked, latency-compensated cueing through a consumer vibration motor.** A band-pass filter re-centred on the spectral peak feeds an online dominant-axis projection (Oja's rule) and a WFLC tracker. The cue fires when the phase predicted one actuator latency ahead crosses the target, at most once per cycle, and the pulse is shorter than a third of a cycle. A per-user sweep picks the target phase that minimises measured tremor power.
4. **Gate-filtered personal PK/PD forecasting.** Only readings the gate marks as still feed a per-minute severity series. That series is fitted with a dose-driven Bateman + effect-site + Emax model whose doses come from a one-tap log. The fitted curve forecasts each dose's wear-off time so the app can warn ahead.
5. **The combination runs in a browser, fully offline,** on a phone or watch. It needs 2,923 model parameters and well under a millisecond per decision on a desktop CPU, with no custom hardware.
