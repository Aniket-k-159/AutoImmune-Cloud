# Assumptions

Every modelling assumption, with the direction it biases results. Stating the
bias direction is what distinguishes a limitations section from a disclaimer.

## Substrate

**A1. Capacity is a scalar.**
Real services are multi-resource (CPU, memory, connection pool, file handles)
and can exhaust one while having slack in others.
*Bias:* understates failure. Real services fail earlier than modelled.

**A2. Requests are homogeneous.**
Every request costs the same. Real traffic mixes cheap reads and expensive
writes.
*Bias:* understates variance. Real load spikes are burstier.

**A3. Topology is static during an episode.**
No autoscaling, no deployments, no service-discovery changes mid-cascade.
*Bias:* removes a negative feedback loop. Autoscaling with a provisioning lag is
delayed negative feedback and could produce oscillation instead of collapse.
Named as the primary extension.

**A4. Redistribution is instantaneous.**
Load moves to survivors within one timestep; no queueing delay, no connection
draining.
*Bias:* accelerates the cascade relative to reality, but does not change whether
one occurs.

**A5. Services are binary — up or down.**
Real services degrade gracefully: they shed load, serve cached responses, return
partial results.
*Bias:* overstates damage per failure; understates the duration over which a
degraded service emits anomalous telemetry.

## Fault process

**A6. Faults are independent across services.**
Each service degrades with probability `p` per timestep, independently.
*Bias:* understates real correlated failure (a bad config push, an AZ outage, a
shared dependency). Correlated faults would make the cascade worse, so results
are conservative.

**A7. Faults are indistinguishable by cause.**
A degradation is a degradation, whether caused by a bad deploy, a memory leak,
or a compromised workload. The automation cannot tell them apart.
*Bias:* none — this is the modelling premise, and it matches the operational
reality the project is about.

**A8. A degraded service keeps consuming capacity.**
It does not cleanly stop; it emits errors and holds resources.
*Bias:* gives unremediated faults a real ongoing cost, which is what makes the
detection trade-off genuine rather than one-sided.

## Detector

**A9. Detector characterised by its ROC curve, not trained.**
Benign and degraded telemetry are two overlapping distributions with
separability `d'`.
*Bias:* the significant one. A real detector's errors are **correlated across
similar workloads** — services running the same image under the same load
pattern produce similar scores, so false positives cluster rather than arriving
independently. Clustered false positives make the autoimmune cascade *worse*.
Results under this assumption are therefore conservative on H2.

**A10. Telemetry noise is independent across nodes.**
Follows from A9 and carries the same conservative bias.

**A11. Telemetry score is a monotone function of load ratio `L_i / C_i`.**
This is the coupling that closes the feedback loop — the single most important
modelling choice in the project. The functional form and its strength constant
are choices, not empirical measurements.
*Mitigation:* **sensitivity analysis on this constant is mandatory.** The
U-curve could otherwise be an artefact of one parameter. This is the most
important robustness check in the whole project, and it is the first question a
marker should ask.

## Response

**A12. Quarantine is instantaneous and complete.**
No drain delay, no partial isolation.
*Bias:* makes remediation faster-acting in both directions — better at removing
genuine faults, faster at propagating the autoimmune cascade. Roughly neutral.

**A13. No human in the loop.**
No operator reviews, overrides, or halts the automation.
*Bias:* this is the premise, not a flaw. A human-approval delay on
high-blast-radius actions is a named extension and would test whether slowing
the response helps.

**A14. Fixed quarantine duration `T_q`.**
Real remediation time varies widely.
*Bias:* understates variance in recovery.

## Timing

**A15. Synchronous discrete-time updates.**
All nodes update simultaneously each step; no event queue, no continuous time.
*Bias:* can synchronise failures that would be staggered in reality, potentially
sharpening the observed transition. An event-driven reimplementation (SimPy) is
listed as an extension specifically to test whether this changed any conclusion.
