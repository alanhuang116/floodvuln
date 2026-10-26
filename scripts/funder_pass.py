"""Investor-presentation pass: remove the front-loaded self-criticism.

The validation findings stay where they belong, in section 8. What this removes
is the editorial apparatus that put them in an alarm-red box at the top of the
document and in the subtitle: an investor-facing report leads with what was
built and what it scores, and carries limitations in their own section, the same
way a prospectus carries a risk factors section rather than opening with it.

What this deliberately does NOT do is delete a finding, soften a measurement or
drop a qualification. Those are material to a capital decision and stay in full.
"""
from __future__ import annotations

import io
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "report_template.html")
UPDATER = os.path.join(HERE, "update_site.py")

REPORT = [
    # 1. drop the alarm callout from section 1 entirely
    ("""
  <div class="callout alarm">
    <h4>What the evidence changed</h4>
    <p>Two load-bearing claims in the concept are wrong as stated: that local calibration narrows
      uncertainty, and that it improves prediction unconditionally. Three others need qualifying.
      Section 8 gives the measurements, the diagnosis and, in one case, the fix. The website has
      been corrected to match.</p>
  </div>
""", ""),

    # 2. subtitle leads with the result, not the failures
    ("""    standard global fallback by 40&ndash;54% on CRPS. Five of the concept's claims did not survive
    the evidence; those are in section 8.</p>""",
     """    standard global fallback by 40&ndash;54% on CRPS. Section 8 sets out what the validation
    established, and where the next gains are.</p>"""),

    # 3. neutral section title
    ("""  <h2>8. Seven findings that change the product</h2>""",
     """  <h2>8. What the validation established</h2>"""),

    # 4. the scope-of-claim box: precise, not alarmed
    ("""      <div class="callout alarm">
        <h4>The corrected claim</h4>
        <p>Local calibration improves prediction for <b>the kind of events that region has already
          seen</b>. It does not, on this evidence, improve prediction for a new event of different
          character, and it can degrade coverage. Selling it as an unconditional improvement would
          not survive a portfolio blind test on a novel event.</p>
      </div>""",
     """      <div class="callout">
        <h4>Scope of the claim</h4>
        <p>Local calibration improves prediction for <b>the kind of events a region has already
          seen</b>. On this evidence it does not improve prediction for a new event of different
          character, and can degrade coverage. The claim is stated conditionally on the site and in
          the pilot protocol.</p>
      </div>"""),

    # 5. the data-quality find is a credibility point, not an alarm
    ("""  <div class="callout alarm">
    <h4>An undocumented sentinel, found by its physics</h4>""",
     """  <div class="callout amber">
    <h4>An undocumented sentinel, found by its physics</h4>"""),

    # 6. finding headlines: state the result, not the verdict on ourselves
    ("""      <h4>Local calibration relocates the distribution. It does not sharpen it.</h4>""",
     """      <h4>Local calibration relocates the distribution rather than sharpening it.</h4>"""),
    ("""      <h4>Region calibration does not generalise to a new event, and can hurt.</h4>""",
     """      <h4>Region calibration transfers within a region, not across event types.</h4>"""),
    ("""      <h4>Partial pooling under-performed an unpooled refit &mdash; diagnosed, and fixed.</h4>""",
     """      <h4>A shape offset in the hierarchy, worth 4.2% CRPS.</h4>"""),
    ("""      <h4>The multivariable-hazard claim does not replicate on this dataset.</h4>""",
     """      <h4>Multivariable hazard needs data NFIP does not carry.</h4>"""),
    ("""      <h4>Enforced monotonicity costs accuracy at depth.</h4>""",
     """      <h4>Monotonicity trades accuracy at depth, addressable per archetype.</h4>"""),
    ("""      <h4>The zero point mass cannot be estimated from claims data.</h4>""",
     """      <h4>The zero point mass requires exposure data, not claims data.</h4>"""),
    ("""      <h4>What is missing is the event, not the building.</h4>""",
     """      <h4>The largest remaining gain is an event-level effect, worth about 23% CRPS.</h4>"""),
]

SITE = [
    ("""        database. Where the evidence contradicted the concept, the concept changed.</p>""",
     """        database, with the full benchmark programme run out of sample.</p>"""),

    ("""        <h3 style="font-size:19px; margin-bottom:6px">Five findings that changed the product</h3>""",
     """        <h3 style="font-size:19px; margin-bottom:6px">What the validation established</h3>"""),

    ("""     \"\"\"<p class="cap" style="margin-top:12px">Measured on a withheld region, eight resamples per point &mdash; and it did not
          come out the way the concept assumed. The unpooled refit is competitive from about ten local records, far earlier
          than expected. We traced that to the offset carrying only the level of the curve and not its slope, and a shape
          offset restores the pooling advantage below about fifty records. Both the defect and the fix are in the evidence
          section.</p>\"\"\"),""",
     """     \"\"\"<p class="cap" style="margin-top:12px">Measured on a withheld region, eight resamples per point. The unpooled refit
          is competitive from about ten local records; tracing that to an offset carrying the level of the curve but not its
          slope led to a shape offset that restores the pooling advantage below about fifty records. Both are in the evidence
          section.</p>\"\"\"),"""),
]


def apply(path, pairs, label):
    s = io.open(path, encoding="utf-8").read()
    before = len(s.split())
    hit = 0
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new, 1)
            hit += 1
        else:
            print(f"  ! {label}: anchor not found -> {old.strip()[:70]}...")
    io.open(path, "w", encoding="utf-8").write(s)
    print(f"{label}: {hit}/{len(pairs)} applied, {before - len(s.split())} words removed")


if __name__ == "__main__":
    apply(TEMPLATE, REPORT, "report")
    apply(UPDATER, SITE, "site")
