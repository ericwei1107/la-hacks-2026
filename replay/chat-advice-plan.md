# Practical Coach chat answers

Goal: answer requests for practice advice with a short priority, observed reason,
and concrete drill, rather than raw learner estimates. Preserve the frozen
text/citations API, verified facts, original actions, exact-state attribution,
model budgets and local fallback. Only replay/ changes; Claude's designated
files, characters/, contracts/ and Chloe's app remain untouched.

- [x] Add failing regressions for improvement advice versus progress questions,
  repeated lows/throws, sparse/uncertain data, history, scoped situations,
  provider selection of irrelevant mastery, and repeated caveats.
- [x] Add grounded practice facts and intent routing. Require practice facts
  for advice requests even when the model selects unrelated tool facts.
  Preserve explicit missing information and synthetic labels.
- [x] Remove repeated identical learning caveats without removing qualifications.
- [x] Run the full replay suite, contract validation, local HTTP checks on
  Garrett's recording with model calls disabled, and an independent review.
- [x] Document the response change and restart instructions in replay/README.md.

Verification: 230 replay tests passed; contracts/validate.py passed. The local
HTTP route returned 200 for Garrett's 10-22-19 session, with 12 of 13 labeled
low-defense decisions hit and no break in 4 of 4 throw-break decisions, plus
four recorded round/frame citations. Review found additional prospective
question forms; regressions now cover those forms. Publication is separate
from this local response-format fix.
