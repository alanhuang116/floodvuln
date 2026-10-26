"""Editorial pass for an investor audience.

Trims verbosity and self-narrating framing from the report template and the
website copy. Every number, table, figure and finding is preserved: an investor
reading a validation report needs the negative results more than the positive
ones, so this cuts words, not evidence.

Run before make_report.py / update_site.py. Idempotent: a replacement whose
anchor is already gone is reported and skipped.
"""
from __future__ import annotations

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
TEMPLATE = os.path.join(HERE, "report_template.html")
UPDATER = os.path.join(HERE, "update_site.py")

# ---------------------------------------------------------------- report
REPORT_TRIMS = [
    # --- masthead -------------------------------------------------------
    ("""  <h1>FloodVuln Global:<br>what happened when<br>we actually built it.</h1>
  <p class="sub">A working implementation of the flood vulnerability platform described in the
    product white paper, calibrated against 1.86 million public flood-insurance claims and the
    published JRC global depth&ndash;damage database, with the benchmark programme run end to end.
    Five of the concept's claims did not survive contact with the evidence, including one on the
    website's front page. They are reported here rather than buried.</p>""",
     """  <h1>FloodVuln Global:<br>built, calibrated,<br>measured.</h1>
  <p class="sub">The flood vulnerability platform from the product white paper, implemented and
    calibrated against 1.86 million public flood-insurance claims and the published JRC global
    depth&ndash;damage database, with the full benchmark programme run out of sample. It beats the
    standard global fallback by 40&ndash;54% on CRPS. Five of the concept's claims did not survive
    the evidence; those are in section 8.</p>"""),

    # --- the confessional callout ---------------------------------------
    ("""    <h4>Read this before the results</h4>
    <p>Five claims in the product concept are not supported by the data, and two of them are load
      bearing: that local calibration narrows uncertainty, and that it improves prediction
      unconditionally. Both are wrong as stated. They are set out in section 8 and the website has
      been corrected. A platform whose selling point is transparent benchmarking does not get to
      quietly drop the benchmarks that went against it.</p>""",
     """    <h4>What the evidence changed</h4>
    <p>Two load-bearing claims in the concept are wrong as stated: that local calibration narrows
      uncertainty, and that it improves prediction unconditionally. Three others need qualifying.
      Section 8 gives the measurements, the diagnosis and, in one case, the fix. The website has
      been corrected to match.</p>"""),

    # --- scope ----------------------------------------------------------
    ("""  <p>The brief asked for calibration against all available datasets. What is genuinely available to
    an automated build, without a licence negotiation or a signed data agreement, turned out to be a
    much smaller set than the white paper's source inventory implies. That gap is itself a finding,
    because it is the same gap a real product team hits in month one.</p>""",
     """  <p>What is available to an automated build, without a licence negotiation or a data agreement, is
    a much smaller set than the white paper's source inventory implies &mdash; the same gap a product
    team hits in month one.</p>"""),

    ("""    <h4>On not scraping</h4>
    <p>Two of the missing sources are public documents behind a bot filter, and two require a licence.
      A build script that routed around either would have produced a better-looking report and an
      unusable product. The register above records the refusal rather than hiding it.</p>""",
     """    <h4>On not scraping</h4>
    <p>Two missing sources sit behind a bot filter, two require a licence. Routing around either would
      have produced a better-looking report and an unusable product.</p>"""),

    # --- literature -----------------------------------------------------
    ("""  <p>The review was run to settle specific design questions, not to produce a citation list.</p>""",
     """  <p>The review settled three design questions.</p>"""),

    ("""  <p>Wing et&nbsp;al. (2020) analysed over two million NFIP claims and found that observed losses are
    not a monotonic function of depth in the individual, and are better described by a beta
    distribution that is frequently bimodal at a given depth. That is a direct argument for a bounded
    distribution with mass at the endpoints. Recent work has converged on exactly this: the 2026
    NHESS study of flood damage functions for rice uses a Bayesian <i>zero-and-one-inflated beta</i>
    and scores it with CRPS, MAE and mean bias error &mdash; the same family and the same metrics
    adopted here. That study also reports the ordering deterministic stage&ndash;damage &lt;
    probabilistic stage&ndash;damage &lt; Bayesian regression &lt; random forest, which sets a
    realistic expectation for how much a probabilistic model should win by.</p>""",
     """  <p>Wing et&nbsp;al. (2020), on over two million NFIP claims, found observed losses are not
    monotonic in depth at the individual level and are better described by a beta distribution,
    frequently bimodal at a given depth &mdash; an argument for a bounded distribution with mass at
    the endpoints. The 2026 NHESS study of rice damage functions uses the same
    <i>zero-and-one-inflated beta</i> family and the same CRPS/MAE/bias metrics adopted here, and
    reports the ordering deterministic &lt; probabilistic &lt; Bayesian &lt; random forest, which
    sets a realistic expectation for the size of the win.</p>"""),

    ("""  <p>Wagenaar et&nbsp;al. (2018) showed that multivariable damage models transfer better when updated
    with data from the destination region, which is the case for partial pooling rather than either
    a fixed global curve or an unpooled local refit. Gerl et&nbsp;al. (2016), reviewing 61 sources
    and nearly a thousand functions, found strong heterogeneity and limited explicit validation,
    which is the case for a harmonisation layer with provenance.</p>""",
     """  <p>Wagenaar et&nbsp;al. (2018): multivariable models transfer better when updated with
    destination-region data &mdash; the case for partial pooling over either a fixed global curve or
    an unpooled local refit. Gerl et&nbsp;al. (2016): 61 sources, nearly a thousand functions, strong
    heterogeneity, limited validation &mdash; the case for a harmonisation layer with provenance.</p>"""),

    ("""  <p>Wagenaar et&nbsp;al. (2017) reported roughly a 20% mean-absolute-error reduction from adding
    hazard and building variables to a depth-only model. That claim was treated as a hypothesis to
    test rather than a result to repeat, and section 8 reports what happened.</p>""",
     """  <p>Wagenaar et&nbsp;al. (2017) reported roughly 20% MAE reduction from adding hazard and building
    variables. Treated here as a hypothesis to test, not a result to repeat; see section 8.6.</p>"""),

    # --- harmonisation --------------------------------------------------
    ("""  <p>The specification calls depth-reference harmonisation critical. It understates the case. Three
    ambiguities in the source data each move the fitted curve more than any modelling choice made
    later.</p>""",
     """  <p>Three ambiguities in the source data each move the fitted curve more than any modelling choice
    made later.</p>"""),

    ("""  <p>Adopted rule: values with magnitude at or below 11 are feet; 12 and above are inches; exactly 12
    is flagged ambiguous and excluded from primary calibration, because it is the one point where the
    two populations overlap and its mean damage ratio (0.49) sits between the 1&nbsp;ft value (0.25)
    and the 10&nbsp;ft value (0.72), which is the signature of a mixture.</p>""",
     """  <p>Adopted rule: magnitude at or below 11 is feet; 12 and above is inches; exactly 12 is flagged
    ambiguous and excluded, being the one point where the populations overlap &mdash; its mean damage
    ratio (0.49) sits between the 1&nbsp;ft value (0.25) and the 10&nbsp;ft value (0.72).</p>"""),

    # --- model ----------------------------------------------------------
    ("""  <p>The ZOIB log-likelihood separates into a categorical part over {0, (0,1), 1} and a beta part over
    the interior, and the beta density depends on the interior observations only through <i>n</i>,
    &sum;log&thinsp;<i>x</i> and &sum;log(1&minus;<i>x</i>). Binning by depth therefore yields
    <i>sufficient statistics</i> rather than an approximation. Fitting 1.86 million claims costs the
    same as fitting a hundred cells, which is what makes the twenty-fold benchmark programme
    affordable. A property test confirms the binned likelihood is stable to within 5&times;10&#8315;&sup3;
    relative across a 25-fold change in bin width.</p>""",
     """  <p>The ZOIB log-likelihood separates into a categorical part over {0, (0,1), 1} and a beta part
    whose density depends on the interior observations only through <i>n</i>,
    &sum;log&thinsp;<i>x</i> and &sum;log(1&minus;<i>x</i>). Binning by depth therefore yields
    <i>sufficient statistics</i>, not an approximation: fitting 1.86 million claims costs what fitting
    a hundred cells costs, which is what makes a twenty-fold benchmark programme affordable. A
    property test confirms stability to 5&times;10&#8315;&sup3; across a 25-fold change in bin width.</p>"""),

    ("""    <p>The moment estimator returned a between-unit scale of 3.4 and 7.5 for the two inflation
      components. That is not evidence of real between-group variation; it is an unidentified
      parameter wandering, because the zero and one components sit near the boundary in claims data.
      Left uncapped it would have switched shrinkage off exactly where shrinkage is most needed. The
      ceiling is documented in the code with this reasoning attached.</p>""",
     """    <p>The moment estimator returned a between-unit scale of 3.4 and 7.5 for the two inflation
      components &mdash; not real between-group variation but an unidentified parameter wandering,
      because those components sit near the boundary in claims data. Uncapped it would switch
      shrinkage off exactly where shrinkage is needed.</p>"""),

    ("""  <p>Aleatory spread is the fitted ZOIB itself. Epistemic spread is the posterior of the group offset
    under the shrinkage prior, Cov = (H + diag(1/&tau;&sup2;))&#8315;&sup1;, so a region with one
    observation inherits the prior variance and a region with sixty thousand collapses to the
    likelihood. This matters more than it sounds: with 1.86 million records the <i>global</i>
    parameter vector is pinned down and contributes under 0.001, so an implementation that reported
    only parameter uncertainty would have reported approximately zero everywhere and called it
    calibrated.</p>""",
     """  <p>Aleatory spread is the fitted ZOIB. Epistemic spread is the posterior of the group offset under
    the shrinkage prior, Cov = (H + diag(1/&tau;&sup2;))&#8315;&sup1;, so a region with one
    observation inherits the prior variance and one with sixty thousand collapses to the likelihood.
    With 1.86 million records the <i>global</i> parameter vector contributes under 0.001 &mdash; an
    implementation reporting only parameter uncertainty would report approximately zero everywhere
    and call it calibrated.</p>"""),

    ("""  <p>Before touching real data the fitter was tested against synthetic data drawn from a known ZOIB
    with 200,000 observations. Maximum absolute error on the recovered mean curve across
    &minus;0.5 to 5&nbsp;m was <b>0.0019</b>, with p&#8320; and p&#8321; recovered to three decimal
    places. Twenty-two property tests cover monotonicity under random parameters, quantile&ndash;CDF
    inversion, closed-form moments against simulation, CRPS reduction to absolute error for a
    degenerate forecast, and every harmonisation rule.</p>""",
     """  <p>Tested first against synthetic data from a known ZOIB, 200,000 observations: maximum absolute
    error on the recovered mean curve across &minus;0.5 to 5&nbsp;m was <b>0.0019</b>, with
    p&#8320; and p&#8321; recovered to three decimals. Twenty-two property tests cover monotonicity
    under random parameters, quantile&ndash;CDF inversion, closed-form moments against simulation,
    CRPS reduction to absolute error, and every harmonisation rule.</p>"""),

    # --- results --------------------------------------------------------
    ("""  <p>Fitted mean damage ratio at 0.91&nbsp;m above the lowest floor: manufactured home 0.517,
    single-family one-storey slab 0.451, one-storey crawlspace 0.363, two-storey slab 0.325,
    elevated with enclosure 0.261, two-storey with basement 0.254. The ordering is not imposed. It
    reproduces the physical expectation that a second storey puts more value above the water and that
    elevation works, and it recovers the modifiers Wing et&nbsp;al. identified as material:
    occupancy, storeys and foundation.</p>""",
     """  <p>Fitted mean damage ratio at 0.91&nbsp;m above the lowest floor: manufactured home 0.517,
    one-storey slab 0.451, one-storey crawlspace 0.363, two-storey slab 0.325, elevated with
    enclosure 0.261, two-storey with basement 0.254. The ordering is not imposed. It reproduces the
    expectation that a second storey puts more value above the water and that elevation works, and
    recovers the modifiers Wing et&nbsp;al. found material: occupancy, storeys, foundation.</p>"""),

    ("""  <p>The JRC North America residential curve is the fallback the specification nominates for
    countries without local functions. Against 1.86 million US claims it runs high across the usable
    depth range, by roughly 0.2 to 0.3 in absolute damage ratio between 0.5 and 3&nbsp;m. This is not
    a criticism of a global product used as intended, and the JRC curves are normalised to a
    different maximum-damage convention. It is the size of the correction that a local calibration
    layer exists to supply, and it is measurable.</p>""",
     """  <p>The JRC North America residential curve is the specification's nominated fallback for countries
    without local functions. Against 1.86 million US claims it runs high by roughly 0.2 to 0.3 in
    absolute damage ratio between 0.5 and 3&nbsp;m. That is not a criticism of a global product used
    as intended &mdash; the JRC curves use a different maximum-damage convention &mdash; it is the
    size of the correction a calibration layer exists to supply, and it is measurable.</p>"""),

    ("""  <p>Eleven named events withheld one at a time; the model is refitted without the event and predicts
    it. Deterministic curves are scored as degenerate forecasts, so their CRPS is their mean absolute
    error and the comparison is not rigged.</p>""",
     """  <p>Eleven named events withheld one at a time, the model refitted without each. Deterministic
    curves are scored as degenerate forecasts, so their CRPS is their mean absolute error.</p>"""),

    ("""  <p>The probability integral transform should be uniform under a correctly calibrated forecast.
    It is not, on a withheld event, and the direction is informative: observed damage falls
    systematically in the upper part of the predicted distribution, so the model under-predicts.
    Region calibration improves the tilt only slightly, which is the clue that led to the finding in
    section 8.3.</p>""",
     """  <p>The probability integral transform should be uniform under a calibrated forecast. On a withheld
    event it is not, and the direction is informative: observed damage falls in the upper part of the
    predicted distribution, so the model under-predicts. Region calibration barely improves the tilt
    &mdash; the clue behind section 8.3.</p>"""),
]

# ---------------------------------------------------------------- findings
FINDING_TRIMS = [
    ("""      <p>This contradicts the concept's central visual, the calibration ladder captioned
        &ldquo;more evidence narrows uncertainty&rdquo;. At 0.61&nbsp;m for a single-family slab
        dwelling, the P10&ndash;P90 width is 0.670 with no archetype information, 0.723 with the
        archetype, and 0.731 with 63,780 local Florida claims. It gets marginally <i>wider</i>,
        because the width is dominated by genuine building-to-building variability that no amount of
        local data removes. What local evidence does buy is the epistemic component, and that falls
        from 0.111 at the published prior to 0.001 with a large local sample &mdash; a factor of
        about a hundred. The honest claim is: <b>local calibration buys accuracy and calibration, not
        sharpness.</b> The website has been corrected and now reports the two components separately.</p>""",
     """      <p>This contradicts the concept's central visual, the calibration ladder captioned
        &ldquo;more evidence narrows uncertainty&rdquo;. At 0.61&nbsp;m for a single-family slab
        dwelling the P10&ndash;P90 width is 0.670 with no archetype information, 0.723 with the
        archetype and 0.731 with 63,780 local Florida claims &mdash; marginally <i>wider</i>, because
        the width is building-to-building variability that local data cannot remove. What local
        evidence buys is the epistemic component, which falls from 0.111 to 0.001, a factor of about
        a hundred. <b>Local calibration buys accuracy and calibration, not sharpness.</b> The site now
        reports the two components separately.</p>"""),

    ("""      <p>A building that is inundated and suffers no damage rarely becomes an insurance claim, so it
        never enters the file. The second pull recovered only 4,476 zero-damage records against 1.92
        million positive ones, and the fitted P(D&nbsp;=&nbsp;0) is therefore 0.1&ndash;2% &mdash;
        conditional on a claim being filed, and a lower bound on the quantity the product advertises.
        Estimating P(no damage | inundated) requires an exposure file listing every building in the
        flood footprint, which is a client input, not a public one. This strengthens rather than
        weakens the commercial case for the G5 client-view rung, but the API now returns the
        conditioning as an explicit warning instead of a clean number.</p>""",
     """      <p>A building inundated without damage rarely becomes a claim, so it never enters the file. The
        second pull recovered 4,476 zero-damage records against 1.92 million positive ones, so the
        fitted P(D&nbsp;=&nbsp;0) of 0.1&ndash;2% is conditional on a claim being filed &mdash; a
        lower bound on the quantity the product advertises. Estimating P(no damage | inundated) needs
        an exposure file listing every building in the footprint, which is a client input. That
        strengthens the commercial case for the G5 client-view rung; the API now returns the
        conditioning as an explicit warning rather than a clean number.</p>"""),

    ("""      <p>The roadmap consequence is concrete: an event-level random effect, updated from the first
        days of claims, is worth more than any additional per-building covariate available here. That
        is also a saleable capability, because it is exactly what post-event reserving needs.</p>""",
     """      <p>An event-level random effect, updated from the first days of claims, is therefore worth more
        than any additional per-building covariate available here &mdash; and is directly saleable,
        being what post-event reserving needs.</p>"""),

    ("""      <p>The mechanism follows from finding 3. A region offset fitted on that region's history is
        partly absorbing the <i>event composition</i> of that history: Louisiana's offset is
        substantially Katrina, Texas's is substantially Harvey and Allison. Applied to a genuinely
        new event it transfers the wrong severity. Within-region random hold-out, where the future
        resembles the past, still shows the expected gain &mdash; that is what the learning curve in
        section 7.6 measures &mdash; so the honest statement is conditional:</p>""",
     """      <p>The mechanism follows from finding 3: a region offset partly absorbs the <i>event
        composition</i> of that region's history &mdash; Louisiana's offset is substantially Katrina,
        Texas's substantially Harvey and Allison &mdash; so it transfers the wrong severity to a new
        event. Within-region random hold-out, where the future resembles the past, still shows the
        expected gain (section 7.6). The claim is therefore conditional:</p>"""),

    ("""      <p>The fix is not to abandon local calibration but to separate the two things it is currently
        conflating: a persistent regional building-stock effect, which should transfer, and an
        event-severity effect, which should not. That is the same event-level random effect finding 3
        already prices at roughly 23% CRPS.</p>""",
     """      <p>The fix is to separate what the offset currently conflates: a persistent regional
        building-stock effect, which should transfer, and an event-severity effect, which should not.
        That is the event-level random effect finding 3 prices at roughly 23% CRPS.</p>"""),

    ("""      <p>The learning curve inverted the expected ordering. From about ten local records upward, a
        full unpooled refit on the same small sample beat the hierarchical model, which is the
        opposite of what partial pooling exists to do. That is a defect in the implementation, not
        in the concept, and it was worth chasing rather than reporting as a curiosity.</p>""",
     """      <p>The learning curve inverted the expected ordering: from about ten local records upward a full
        unpooled refit beat the hierarchical model, the opposite of what partial pooling exists to do.
        A defect in the implementation, not the concept.</p>"""),

    ("""      <p>The diagnosis is specific. Louisiana's observed response for the largest archetype runs
        0.192, 0.449, 0.668, 0.812 at 0, 0.61, 1.22 and 2.44&nbsp;m &mdash; materially <i>steeper</i>
        than the national average. The four-parameter offset can move the level of a curve but not
        its slope, so it compromises: it over-predicted at 0&nbsp;m (0.289 against 0.192 observed) and
        under-predicted at depth (0.714 against 0.812). An unpooled refit, free to change the shape,
        tracked the data almost exactly. <b>Regional variation lives in the slope of the depth
        response, and the hierarchy only parameterised the level.</b></p>""",
     """      <p>Louisiana's observed response for the largest archetype runs 0.192, 0.449, 0.668, 0.812 at 0,
        0.61, 1.22 and 2.44&nbsp;m &mdash; materially <i>steeper</i> than national. A four-parameter
        offset moves a curve's level but not its slope, so it compromised: over-predicting at
        0&nbsp;m (0.289 against 0.192) and under-predicting at depth (0.714 against 0.812). An
        unpooled refit, free to change shape, tracked the data almost exactly. <b>Regional variation
        lives in the slope, and the hierarchy only parameterised the level.</b></p>"""),

    ("""      <p>The shape offset improves CRPS by about 4.2% at every sample size, and at 10 and 25 local
        records it now <b>beats the unpooled refit</b> &mdash; restoring the ordering the product
        claims, precisely in the sparse-data regime where the claim matters. By a few hundred records
        the two converge, which is the correct behaviour: with enough local data there is nothing
        left for a prior to contribute. The shipped model retains the level-only offset; the shape
        component is implemented and validated but not yet refitted across all 4,483 units, which is
        the first item on the roadmap.</p>""",
     """      <p>The shape offset improves CRPS by about 4.2% at every sample size, and at 10 and 25 local
        records it <b>beats the unpooled refit</b> &mdash; restoring the claimed ordering precisely in
        the sparse-data regime where it matters. The two converge by a few hundred records, which is
        correct: with enough local data a prior has nothing left to contribute. The shipped model
        retains the level-only offset; the shape component is validated but not yet refitted across
        all 4,483 units, and is the first roadmap item.</p>"""),

    ("""      <p><code>floodWaterDuration</code> is recorded on 1.6% of claims, and within every depth band
        the recorded-duration subset shows <i>lower</i> mean damage than the unrecorded majority
        (0.294 against 0.426 above 1.2&nbsp;m). That is a non-random recording process, not a physical
        signal. The cited ~20% MAE improvement from multivariable models is not contradicted &mdash;
        it was obtained on survey data with genuine duration and velocity measurements &mdash; but it
        cannot be claimed on the strength of NFIP. The product should say &ldquo;multivariable where
        the data support it&rdquo; and name the datasets that do.</p>""",
     """      <p><code>floodWaterDuration</code> is recorded on 1.6% of claims, and within every depth band the
        recorded subset shows <i>lower</i> mean damage than the unrecorded majority (0.294 against
        0.426 above 1.2&nbsp;m) &mdash; a non-random recording process, not a physical signal. The
        cited ~20% MAE improvement is not contradicted; it came from survey data with genuine
        duration and velocity. It simply cannot be claimed on NFIP. The product should say
        &ldquo;multivariable where the data support it&rdquo; and name those datasets.</p>"""),

    ("""      <p>Observed mean damage for single-family slab dwellings plateaus above about 1.7&nbsp;m and the
        binned means then wander (0.504 at 1.66&nbsp;m, 0.447 at 2.39&nbsp;m, 0.505 at 3.15&nbsp;m) on
        samples of a few thousand. The monotone constraint holds the fitted curve rising, so it
        over-predicts by up to 0.15 in that range. The specification allows evidence-driven
        exceptions to monotonicity; whether this qualifies is a judgement about whether the plateau is
        real physics (a one-storey house is destroyed once, and deeper water adds nothing) or thin-sample
        noise. It is most likely real, and the fix is a saturating ceiling per archetype rather than
        abandoning monotonicity.</p>""",
     """      <p>Observed mean damage for single-family slab dwellings plateaus above about 1.7&nbsp;m and then
        wanders (0.504 at 1.66&nbsp;m, 0.447 at 2.39&nbsp;m, 0.505 at 3.15&nbsp;m) on samples of a few
        thousand. The monotone constraint holds the fitted curve rising, so it over-predicts by up to
        0.15 there. The plateau is most likely real &mdash; a one-storey house is destroyed once and
        deeper water adds nothing &mdash; and the fix is a per-archetype saturating ceiling, not
        abandoning monotonicity.</p>"""),
]

# ---------------------------------------------------------------- website
SITE_TRIMS = [
    ("""      <p class="lede measure">Everything below is output from a reproducible run in the FloodVuln
        repository against public data: {qn('records ingested')} NFIP claim records from the
        OpenFEMA redacted claims file, and the published JRC global depth&ndash;damage database.
        Where the evidence contradicts the product concept, the concept is what changed.</p>""",
     """      <p class="lede measure">Output from a reproducible run against public data:
        {qn('records ingested')} NFIP claim records and the published JRC global depth&ndash;damage
        database. Where the evidence contradicted the concept, the concept changed.</p>"""),

    ("""        <p class="small">The JRC North America residential curve is the standard fallback where no
          local function exists. Against 1.86 million US claims it runs high across the whole
          usable depth range &mdash; by roughly 0.2 to 0.3 in absolute damage ratio between
          0.5 and 3&nbsp;m. That is not a criticism of a global product used as intended; it is the
          size of the correction a local calibration layer exists to supply.</p>""",
     """        <p class="small">The JRC North America residential curve is the standard fallback where no
          local function exists. Against 1.86 million US claims it runs high by roughly 0.2 to 0.3 in
          absolute damage ratio between 0.5 and 3&nbsp;m &mdash; the size of the correction a
          calibration layer exists to supply.</p>"""),

    ("""      <p class="cap" style="margin-top:12px">Every model scored identically. A deterministic curve is
        treated as a degenerate forecast, so its CRPS is its mean absolute error and the comparison
        is not rigged toward the probabilistic model. Lower is better for MAE, RMSE and CRPS;
        80% coverage should be 0.80 and calibration slope should be 1.0.</p>""",
     """      <p class="cap" style="margin-top:12px">All models scored identically; a deterministic curve is a
        degenerate forecast, so its CRPS is its mean absolute error. Lower is better for MAE, RMSE and
        CRPS; 80% coverage should be 0.80 and calibration slope 1.0.</p>"""),

    ("""      <p class="cap" style="margin-top:12px">Sources marked <i>not obtained</i> were not scraped around.
        Two public documents refused automated retrieval, and two more require a licence or a data
        agreement that a build script has no business bypassing.</p>""",
     """      <p class="cap" style="margin-top:12px">Two public documents refused automated retrieval; two more
        require a licence or data agreement. None were scraped around.</p>"""),
]


def apply(path: str, trims: list, label: str) -> None:
    s = io.open(path, encoding="utf-8").read()
    hit = miss = 0
    words_before = len(s.split())
    for old, new in trims:
        if old in s:
            s = s.replace(old, new, 1)
            hit += 1
        else:
            miss += 1
            print(f"  ! {label}: anchor already gone or changed -> {old.strip()[:64]}...")
    io.open(path, "w", encoding="utf-8").write(s)
    print(f"{label}: {hit} applied, {miss} skipped, "
          f"{words_before - len(s.split())} words removed")


def main() -> None:
    apply(TEMPLATE, REPORT_TRIMS + FINDING_TRIMS, "report")
    apply(UPDATER, SITE_TRIMS, "site")


if __name__ == "__main__":
    main()
