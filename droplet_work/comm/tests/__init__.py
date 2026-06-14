"""comm.tests — offline test suite for the Communication package (Wave 1).

No network, no real PG. The adapter's _api_call is monkeypatched with a fake Bot API; the
engine's resolver is driven with an injected adapter. Run:
  python -m comm.tests.test_telegram_offline
  python -m comm.tests.test_engine_offline
"""
