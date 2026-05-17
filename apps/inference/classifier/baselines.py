from __future__ import annotations

import numpy as np
import pandas as pd

STAGES = ["AWAKE", "CORE", "DEEP", "REM"]


class MajorityBaseline:
    """Always predicts the majority class from training."""

    def __init__(self) -> None:
        self.majority_: str | None = None
        self.rem_prior_: float = 0.0

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "MajorityBaseline":
        counts = y.value_counts()
        self.majority_ = str(counts.idxmax())
        self.rem_prior_ = float((y == "REM").mean())
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.majority_ is None:
            raise RuntimeError("MajorityBaseline not fit")
        return np.full(len(X), self.majority_, dtype=object)

    def predict_proba_rem(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.rem_prior_, dtype="float64")


class HRThresholdBaseline:
    """Predicts REM when HR is elevated+variable vs session baseline."""

    def __init__(self) -> None:
        self.threshold_: float = 0.5
        self.rem_prior_: float = 0.0
        self.non_rem_majority_: str = "CORE"

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "HRThresholdBaseline":
        self.rem_prior_ = float((y == "REM").mean())
        nr = y[y != "REM"]
        if len(nr) > 0:
            self.non_rem_majority_ = str(nr.value_counts().idxmax())

        feat = X["hr_pct_above_baseline"].to_numpy(dtype="float64")
        is_rem = (y == "REM").to_numpy()
        mask = ~np.isnan(feat)
        if mask.sum() == 0:
            self.threshold_ = 0.5
            return self

        feat_v = feat[mask]
        y_v = is_rem[mask]
        # candidate thresholds: quantiles, plus a coarse grid
        qs = np.quantile(feat_v, np.linspace(0.05, 0.95, 19))
        cands = np.unique(np.concatenate([qs, np.linspace(0.1, 0.9, 17)]))
        best_f1 = -1.0
        best_t = 0.5
        for t in cands:
            pred = feat_v > t
            tp = int(np.sum(pred & y_v))
            fp = int(np.sum(pred & ~y_v))
            fn = int(np.sum(~pred & y_v))
            if tp == 0:
                f1 = 0.0
            else:
                prec = tp / (tp + fp)
                rec = tp / (tp + fn)
                f1 = 2 * prec * rec / (prec + rec)
            if f1 > best_f1:
                best_f1 = f1
                best_t = float(t)
        self.threshold_ = best_t
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        feat = X["hr_pct_above_baseline"].to_numpy(dtype="float64")
        pred_rem = np.where(np.isnan(feat), False, feat > self.threshold_)
        return np.where(pred_rem, "REM", self.non_rem_majority_).astype(object)

    def predict_proba_rem(self, X: pd.DataFrame) -> np.ndarray:
        feat = X["hr_pct_above_baseline"].to_numpy(dtype="float64")
        out = np.where(np.isnan(feat), self.rem_prior_, (feat > self.threshold_).astype("float64"))
        return out.astype("float64")


class RandomBaseline:
    """Predicts each class with its training-set prior. Seeded for reproducibility."""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.classes_: np.ndarray | None = None
        self.priors_: np.ndarray | None = None
        self.rem_prior_: float = 0.0
        self._rng = np.random.default_rng(seed)

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "RandomBaseline":
        counts = y.value_counts()
        self.classes_ = np.array(counts.index.tolist(), dtype=object)
        self.priors_ = (counts.values / counts.sum()).astype("float64")
        self.rem_prior_ = float((y == "REM").mean())
        self._rng = np.random.default_rng(self.seed)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if self.classes_ is None or self.priors_ is None:
            raise RuntimeError("RandomBaseline not fit")
        return self._rng.choice(self.classes_, size=len(X), p=self.priors_)

    def predict_proba_rem(self, X: pd.DataFrame) -> np.ndarray:
        return np.full(len(X), self.rem_prior_, dtype="float64")
