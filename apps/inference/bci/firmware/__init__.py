"""Off-CI firmware/Pi reference for the BCI edge lane.

bci/ is on the CI pytest paths, but this subdir carries no test_*.py so nothing is
collected here (`pytest bci/firmware --collect-only` finds zero tests). The stub
imports the real bci.bandpower + sensors.eeg_adapter so it shares the exact semantic
contract the lane consumes.
"""
