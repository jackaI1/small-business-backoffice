# Decision note for a fictional business owner

**Recommendation:** Pilot rules-assisted intake using synthetic claims. It makes missing details and conflicts visible before an adjuster starts work, preserves repeated submissions and gives a reviewer a clear pending queue. Do not approve a production rollout on this demonstration alone.

I compared three ways of handling 1,000 incoming submissions per month. All money below is CAD. These are transparent planning estimates, not vendor quotes or observed insurer results. The baseline assumes 12 handling minutes per submission; a spreadsheet assumes 8. Assisted intake assumes 3 minutes for a clean submission and 12 for one requiring review, with 30% needing review. Each figure includes average handling/follow-up time, but excludes the adjuster's later investigation.

| Option | Setup | Annual running cost | First year cost | Handling hours/month | Submissions per 160-hour worker month |
| --- | ---: | ---: | ---: | ---: | ---: |
| Manual checklist | $0 | $108,000 | $108,000 | 200 | 800 |
| Shared spreadsheet | $2,400 | $73,560 | $75,960 | 133.33 | 1,200 |
| Rules-assisted intake | $7,200 | $54,480 | $61,680 | 95 | 1,684 |

Estimates use $45/hour for handling and $60/hour for setup/maintenance. Spreadsheet setup is 40 hours, maintenance 2 hours/month and tools $10/month. Assisted setup is 120 hours, maintenance 4 hours/month and hosting $25/month. Manual setup and tools are assumed already available. Setup is implementation/training time, not my measured coding hours. Capacity is theoretical active handling time, before breaks, absences or uneven arrival rates; 200 hours means more than one 160-hour worker month.

At the base assumptions, assisted intake saves 105 handling hours/month (52.5%) and $46,320 in the first year versus manual work. Setup pays back after about 1.6 months from running-cost savings. Saved hours may become capacity rather than cash savings. Compared with the spreadsheet, the first-year estimate is $14,280 lower. This is why I chose a small rules prototype rather than stopping at a checklist.

## Risk and trade-offs

| Option | Main risk | Relative exposure | Mitigation / trade-off |
| --- | --- | --- | --- |
| Manual checklist | Missed checks and duplicate entry; absent clerk loses context | High process risk, low build risk | Train staff and inspect samples; labour grows with volume |
| Shared spreadsheet | Accidental edits, weak change history, inconsistent formulas | Medium process risk, low/medium build risk | Protect formulas and retain versions; concurrent ownership remains awkward |
| Rules-assisted intake | Wrong rules route work incorrectly; outages stop batch entry; false duplicate flags add review | Lower repeat-check risk, higher implementation risk | Keep people in control, preserve payloads, test boundaries, reconcile queue; invest in production controls |

These ratings are qualitative judgments for the fictional scenario, not measured probabilities or monetized expected losses. A spreadsheet is a reasonable lower-cost choice at low volume or where there is no owner for rules maintenance.

## Sensitivity and stop conditions

Average assisted minutes = `3 × (1 − review share) + 12 × review share`. First-year cost = `setup hours × 60 + 12 × (monthly submissions × minutes / 60 × 45 + maintenance hours × 60 + monthly tools)`. [options.json](../reports/options.json) contains the reproducible calculations for all three options.

At 60% review, assisted handling rises to 140 hours/month and first-year cost to $85,980. At 100% review it costs $118,380, above the $108,000 manual baseline. At the base review share, assisted intake beats manual cost only above about 183 submissions/month (184 whole submissions). It beats the spreadsheet above about 310/month (311 whole submissions). These thresholds include setup spread over the first year and exclude financing, taxes and migration costs.

The supplied 12-claim fixture deliberately includes difficult cases: 2 route to an adjuster and 10 need review. That 83.3% fixture review rate is **not** an estimate of real arrivals, and must not be used as evidence for the 30% planning assumption. I measured correctness on the fixture, not handling time or employee productivity.

Before proceeding: confirm each requirement and rule with an actual process owner, collect handling times and review rates from a representative pilot, and check the model again. Require all 15 requirements to pass QA, no missing queue items, an assigned follow-up owner and successful recovery of a database backup. If review remains near 100%, or the volume falls below the break-even range, retain the manual/spreadsheet approach. A real rollout also needs identity/access controls, privacy/retention decisions, policy integration and attachment verification, which this prototype does not provide.
