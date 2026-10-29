"""Session-level purchase-propensity models: which behaviours predict conversion?

Two models, scored on a stratified hold-out set:
  * logistic regression (one-hot + scaling): an interpretable baseline
  * histogram gradient boosting: catches non-linear effects and interactions

Leakage guard: funnel-step flags (cart, checkout) are never used as features.
Features that partly encode the outcome can be switched off with
include_outcome_proxies=False: UCI PageValues (computed from pages that come
before a transaction) and GA4 pageviews/engagement (checkout pages inflate
both). With them off, the GA4 model uses only what is known when the session
starts (channel, device, country, new vs returning, timing), so it answers
"who should we target?" rather than "who is buying right now?".
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

UCI_NUMERIC = [
    "Administrative", "Administrative_Duration", "Informational", "Informational_Duration",
    "ProductRelated", "ProductRelated_Duration", "BounceRates", "ExitRates", "PageValues",
    "SpecialDay",
]
UCI_CATEGORICAL = ["Month", "OperatingSystems", "Browser", "Region", "TrafficType",
                   "VisitorType", "Weekend"]
GA4_NUMERIC = ["pageviews", "engagement_sec"]
GA4_CATEGORICAL = ["channel", "device", "region", "visitor_type", "is_weekend", "month_label"]


@dataclass
class ModelResult:
    metrics: pd.DataFrame
    deciles: pd.DataFrame
    importance: pd.DataFrame
    features: list[str]
    n_train: int
    n_test: int
    base_rate: float


def load_features(con, dataset: str, include_outcome_proxies: bool = True):
    if dataset == "uci":
        df = con.execute("SELECT * FROM uci_features").df()
        y = df["Revenue"].astype(bool).astype(int).to_numpy()
        num = [c for c in UCI_NUMERIC if include_outcome_proxies or c != "PageValues"]
        cat = UCI_CATEGORICAL
    else:
        df = con.execute(
            "SELECT * FROM fct_sessions WHERE dataset = ?", [dataset]
        ).df()
        y = df["s_purchase"].astype(bool).astype(int).to_numpy()
        top = df["region"].value_counts().index[:15]
        df["region"] = df["region"].where(df["region"].isin(top), "Other")
        num = GA4_NUMERIC if include_outcome_proxies else []
        cat = GA4_CATEGORICAL
    X = df[num + cat].copy()
    for c in cat:
        X[c] = X[c].astype(str)
    return X, y, num, cat


def _lift_deciles(y_true, score) -> pd.DataFrame:
    d = pd.DataFrame({"y": y_true, "s": score})
    d["decile"] = pd.qcut(d["s"].rank(method="first", ascending=False), 10, labels=range(1, 11))
    g = d.groupby("decile", observed=True).agg(sessions=("y", "size"), purchases=("y", "sum"),
                                               avg_score=("s", "mean")).reset_index()
    g["conversion_rate"] = g["purchases"] / g["sessions"]
    g["lift"] = g["conversion_rate"] / d["y"].mean()
    g["cum_capture"] = g["purchases"].cumsum() / g["purchases"].sum()
    return g


def train(con, dataset: str, include_outcome_proxies: bool = True, seed: int = 42,
          max_rows: int = 150_000) -> ModelResult:
    X, y, num, cat = load_features(con, dataset, include_outcome_proxies)
    if len(X) > max_rows:  # keep the dashboard responsive on the full GA4 export
        idx = np.random.default_rng(seed).choice(len(X), max_rows, replace=False)
        X, y = X.iloc[idx].reset_index(drop=True), y[idx]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, stratify=y, random_state=seed)

    logit = Pipeline([
        ("prep", ColumnTransformer([
            ("num", StandardScaler(), num),
            ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=20), cat),
        ])),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=0.5)),
    ])
    gbm = Pipeline([
        ("prep", ColumnTransformer([
            ("num", "passthrough", num),
            ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1), cat),
        ])),
        ("clf", HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.06, max_leaf_nodes=31, l2_regularization=1.0,
            categorical_features=list(range(len(num), len(num) + len(cat))),
            early_stopping=True, random_state=seed,
        )),
    ])

    rows, scores = [], {}
    for name, pipe in (("Logistic regression", logit), ("Gradient boosting", gbm)):
        pipe.fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        scores[name] = p
        top10 = _lift_deciles(y_te, p).iloc[0]
        rows.append({
            "model": name,
            "roc_auc": roc_auc_score(y_te, p),
            "pr_auc": average_precision_score(y_te, p),
            "brier": brier_score_loss(y_te, p),
            "top_decile_lift": top10["lift"],
            "top_decile_capture": top10["cum_capture"],
        })
    metrics = pd.DataFrame(rows)
    best = metrics.sort_values("pr_auc", ascending=False).iloc[0]["model"]
    best_pipe = gbm if best == "Gradient boosting" else logit

    sample = min(len(X_te), 6000)
    imp = permutation_importance(
        best_pipe, X_te.iloc[:sample], y_te[:sample], scoring="average_precision",
        n_repeats=5, random_state=seed, n_jobs=1,
    )
    importance = pd.DataFrame({
        "feature": X.columns, "importance": imp.importances_mean, "std": imp.importances_std,
    }).sort_values("importance", ascending=False, ignore_index=True)

    return ModelResult(
        metrics=metrics.assign(best=metrics["model"] == best),
        deciles=_lift_deciles(y_te, scores[best]),
        importance=importance,
        features=list(X.columns),
        n_train=len(X_tr), n_test=len(X_te), base_rate=float(y.mean()),
    )
