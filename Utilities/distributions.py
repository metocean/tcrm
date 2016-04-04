import numpy as np

def gauss(x, sig, mu=0):
    """
    Return x from a gaussian distribution

    :param x: Array like
    :param mu: mean of normal distribution
    :param sig: standard deviation of normal distribution
    """

    return np.exp(-np.power(x - mu, 2.) / (2 * np.power(sig, 2.)))

def tophat(x, delta):
    """
    Return x from a gaussian distribution

    :param x: Array like
    :param delta: value < delta set to 1
    """
    ret = np.zeros_like(x)
    ret[np.abs(x) < delta] = 1
    return ret

def convolved(x, sig):
    return np.max(gauss(x, sig), tophat(x, sig))