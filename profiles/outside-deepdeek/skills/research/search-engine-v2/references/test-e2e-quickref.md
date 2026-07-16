#!/usr/bin/env python3
"""End-to-end test suite for search-engine-v2 structural fixes.

Run:  cd scripts && python test_e2e.py -v
Tests: T1(pipeline_check) T2(RateLimiter) T3(ScraplingPool) T4(extract_single) T5(batch) T6(auto-pipeline) T7(true_coverage)

Key test: T2 verifies RateLimiter sleep-inside-lock pattern — 8 threads × 50ms delay must serialize to ≥0.30s.
Initial fix (sleep outside lock) failed: 0.05s (threads bypassed). Correct fix: sleep inside the same critical section.
