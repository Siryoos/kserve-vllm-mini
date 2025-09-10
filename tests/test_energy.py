import json
import os
from energy.collector import PowerSample, trapezoidal_wh, run_window_bounds


def test_trapezoidal_simple_square():
    # 100W constant for 10 seconds -> 100W * (10/3600) = 0.2777Wh
    samples = [
        PowerSample(ts=0.0, watts=100.0),
        PowerSample(ts=5.0, watts=100.0),
        PowerSample(ts=10.0, watts=100.0),
    ]
    wh = trapezoidal_wh(samples, 0.0, 10.0)
    assert abs(wh - (100.0 * (10.0 / 3600.0))) < 1e-6


def test_trapezoidal_handles_missing():
    samples = [
        PowerSample(ts=0.0, watts=None),
        PowerSample(ts=5.0, watts=100.0),
        PowerSample(ts=10.0, watts=100.0),
        PowerSample(ts=12.0, watts=None),
    ]
    # Only [5,10] contribute
    wh = trapezoidal_wh(samples, 0.0, 12.0)
    assert abs(wh - (100.0 * (5.0 / 3600.0))) < 1e-6


def test_window_bounds_from_requests():
    rows = [
        {"start_ms": 1000.0, "latency_ms": 500.0},
        {"start_ms": 4000.0, "latency_ms": 1000.0},
    ]
    t0, t1 = run_window_bounds(rows)
    assert t0 == 1.0
    assert t1 == (5.0)  # 4s start +1s latency

