import numpy as np
from scipy.stats import norm


def bs_gamma(S, K, T, r, sigma):
    """Vectorized Black-Scholes gamma."""
    with np.errstate(divide="ignore", invalid="ignore"):
        sqrt_T = np.sqrt(T)
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * sqrt_T)
        gamma = norm.pdf(d1) / (S * sigma * sqrt_T)
    return np.nan_to_num(gamma, nan=0.0, posinf=0.0, neginf=0.0)


def bs_delta(S, K, T, r, sigma, is_call=True):
    """Vectorized Black-Scholes delta.  Calls: N(d1), puts: N(d1)-1."""
    with np.errstate(divide="ignore", invalid="ignore"):
        sqrt_T = np.sqrt(T)
        d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * sqrt_T)
        delta = norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0
    return np.nan_to_num(delta, nan=0.0, posinf=0.0, neginf=0.0)