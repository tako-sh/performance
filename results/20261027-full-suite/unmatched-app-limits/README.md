# Initial run with unmatched backend limits

Run 40422659586 completed all 135 cases, but Tako managed apps had a 4,096 file-descriptor limit while directly launched backends inherited 131,072. These results are retained as investigation evidence and excluded from the refreshed public comparison. The complete rerun matches all backends at 65,535 and records the limits throughout measurement.

The original app CPU metric also loses exited processes’ cumulative CPU and can become negative after restarts. Its strict validator rejects those rows. The corrected run uses cumulative app cgroup CPU counters; the raw original values are retained unchanged.
