# Analysis Data

Datasets and generated outputs used by the Python analysis suite. **These files are gitignored** to keep the repo light. Reproduce or fetch them as described below.

## Datasets

### Walch et al. Apple Watch sleep-accel dataset (~86 MB)

Used as a training/validation dataset for the sleep-stage classifier. **Not committed to git.** Download from PhysioNet:

- **Source:** https://physionet.org/content/sleep-accel/1.0.0/
- **License:** Open Data Commons Attribution License v1.0 (see `LICENSE.txt` in the dataset)
- **Citation:** Walch, O., Huang, Y., Forger, D., & Goldstein, C. (2019). *Sleep stage prediction with raw acceleration and photoplethysmography heart rate data derived from a consumer wearable device.* Sleep, 42(12).

To download:

```bash
cd apps/inference/analysis/data
wget -r -N -c -np https://physionet.org/files/sleep-accel/1.0.0/
mv physionet.org walch_apple_watch
```

Or use the PhysioNet CLI if you have it (`wfdb` package).

## Generated outputs

PNG plots (`correlations.png`, `epoch_heatmap.png`, etc.) are produced by the analysis notebooks. **Not committed.** Re-run the relevant notebook (`explore_night.ipynb`, `compare_nights.ipynb`, `train_classifier.ipynb`) to regenerate.
