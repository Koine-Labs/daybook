"""BCI software lane — semantic-first band-power extraction (commitment #11).

The edge (Pi/ESP32) computes band-powers from raw ADC windows and discards the
raw EEG; only semantic band-power packets ride the bus. `bandpower.compute_band_powers`
is the reusable canonical math both the firmware stub and the synthetic test harness
call.
"""
