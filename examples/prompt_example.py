import numpy as np

import bilby
import redback

import matplotlib.pyplot as plt
import matplotlib
matplotlib.rcParams.update(matplotlib.rcParamsDefault)
matplotlib.use("Qt5Agg")

sampler = 'dynesty'
model = 'gaussian'
name = '910505'

redback.get_data.get_prompt_data_from_batse(grb=name)
prompt = redback.transient.prompt.PromptTimeSeries.from_batse_grb_name(name=name)

# use default priors
priors = redback.priors.get_priors(model=model, data_mode='counts', times=prompt.time,
                                   y=prompt.counts, yerr=prompt.counts_err, dt=prompt.bin_size)

result = redback.fit_model(source_type='prompt', model=model, transient=prompt, nlive=500,
                           sampler=sampler, prior=priors, outdir="GRB_results", sample='rslice')
# returns a GRB prompt result object
result.plot_lightcurve(random_models=1000)
result.plot_corner()
