"""TidePay model: features, a softmax classifier over lateness buckets, and federated training.

Pure Python so it runs anywhere the app runs. The model predicts a probability
for each lateness bucket of an open invoice from observable history only (the
customer's earlier invoices that were already settled when the invoice was
issued). Simulated federated averaging with reproducible pairwise additive masks
lets several SMEs train one model without revealing their own updates.
"""
from __future__ import annotations

import json
import math
import random
import statistics
from datetime import date

BUCKETS = ((-99, 0, "on time"), (1, 7, "1-7 days late"), (8, 15, "8-15 days late"),
           (16, 30, "16-30 days late"), (31, 90, "more than 30 days late"))
FEATURES = ("has_history", "log_prior_count", "prior_mean", "prior_std", "prior_late_rate", "prior_long_rate",
            "last_delay", "recent_mean", "trend", "log_size_ratio", "terms", "month_end", "festival_month",
            "portfolio_mean")
FESTIVAL_MONTHS = {2, 3, 4, 6}


def bucket_of(delay):
    for index, (low, high, _label) in enumerate(BUCKETS):
        if low <= delay <= high:
            return index
    return len(BUCKETS) - 1


def features(history, invoice, portfolio_mean):
    """history: settled invoices of the same customer known at issue time, oldest first."""
    delays = [row["delay"] for row in history]
    amounts = [row["amount"] for row in history]
    n = len(delays)
    k = 3  # credibility shrinkage toward the business's own average
    prior_mean = (sum(delays) + k * portfolio_mean) / (n + k)
    recent = delays[-3:] if delays else []
    recent_mean = statistics.fmean(recent) if recent else portfolio_mean
    typical = statistics.fmean(amounts) if amounts else invoice["amount"]
    due = invoice["due_date"]
    return [1.0 if n else 0.0,
            math.log1p(n),
            prior_mean / 10,
            (statistics.pstdev(delays) if n > 1 else 5.0) / 10,
            (sum(1 for d in delays if d > 0) / n) if n else 0.5,
            (sum(1 for d in delays if d > 15) / n) if n else 0.1,
            (delays[-1] if n else portfolio_mean) / 10,
            recent_mean / 10,
            (recent_mean - prior_mean) / 10,
            math.log(max(invoice["amount"], 1) / max(typical, 1)),
            invoice["terms"] / 30,
            1.0 if due.day >= 26 else 0.0,
            1.0 if due.month in FESTIVAL_MONTHS else 0.0,
            portfolio_mean / 10]


def dataset(business):
    """(x, y, delay) rows for one business, using only information available at issue time."""
    rows, settled = [], []
    by_customer = {}
    for invoice in business["invoices"]:
        known = [row for row in settled if row["paid_date"] <= invoice["issue_date"]]
        portfolio = statistics.fmean(row["delay"] for row in known) if known else 5.0
        history = [row for row in by_customer.get(invoice["customer"], []) if row["paid_date"] <= invoice["issue_date"]]
        rows.append((features(history, invoice, portfolio), bucket_of(invoice["delay"]), invoice["delay"]))
        by_customer.setdefault(invoice["customer"], []).append(invoice)
        settled.append(invoice)
    return rows


class Softmax:
    def __init__(self, n_features=len(FEATURES) + 1, n_classes=len(BUCKETS)):
        self.w = [[0.0] * n_features for _ in range(n_classes)]
        self.mean = [0.0] * len(FEATURES)
        self.std = [1.0] * len(FEATURES)
        self.bucket_means = [b[0] if b[0] > -99 else 0 for b in BUCKETS]

    # -- scaling ---------------------------------------------------------
    def fit_scaler(self, xs):
        columns = list(zip(*xs))
        self.mean = [statistics.fmean(column) for column in columns]
        self.std = [statistics.pstdev(column) or 1.0 for column in columns]

    def scale(self, x):
        return [1.0] + [(value - m) / s for value, m, s in zip(x, self.mean, self.std)]

    # -- inference -------------------------------------------------------
    def proba_scaled(self, z):
        logits = [sum(wi * zi for wi, zi in zip(row, z)) for row in self.w]
        top = max(logits)
        exps = [math.exp(value - top) for value in logits]
        total = sum(exps)
        return [value / total for value in exps]

    def proba(self, x):
        return self.proba_scaled(self.scale(x))

    def expected_delay(self, probs):
        return sum(p * m for p, m in zip(probs, self.bucket_means))

    # -- training ----------------------------------------------------------
    def sgd(self, rows, epochs=1, lr=0.05, l2=1e-4, seed=0, start_epoch=0):
        rng = random.Random(seed)
        order = list(range(len(rows)))
        for epoch in range(epochs):
            step = lr / (1 + 0.3 * (start_epoch + epoch))  # decaying learning rate
            rng.shuffle(order)
            for index in order:
                z, y = rows[index]
                probs = self.proba_scaled(z)
                for c, row in enumerate(self.w):
                    gradient = probs[c] - (1.0 if c == y else 0.0)
                    for j in range(len(row)):
                        row[j] -= step * (gradient * z[j] + l2 * row[j])

    def flat(self):
        return [value for row in self.w for value in row]

    def load_flat(self, values):
        width = len(self.w[0])
        self.w = [list(values[i * width:(i + 1) * width]) for i in range(len(self.w))]

    def to_json(self, meta=None):
        return {"model": "TidePay softmax v1", "features": list(FEATURES), "buckets": [b[2] for b in BUCKETS],
                "bucket_ranges": [[b[0], b[1]] for b in BUCKETS], "bucket_means": self.bucket_means,
                "mean": self.mean, "std": self.std, "weights": self.w, "meta": meta or {}}

    @classmethod
    def from_json(cls, data):
        model = cls()
        model.mean, model.std, model.w = data["mean"], data["std"], data["weights"]
        model.bucket_means = data["bucket_means"]
        return model


def pairwise_masks(n_clients, length, round_seed):
    """Illustrative masking, not cryptographic privacy: client i adds mask(i,j) for j>i and subtracts mask(j,i) for j<i; the sum cancels."""
    masks = [[0.0] * length for _ in range(n_clients)]
    for i in range(n_clients):
        for j in range(i + 1, n_clients):
            rng = random.Random(f"{round_seed}:{i}:{j}")
            vector = [rng.uniform(-50, 50) for _ in range(length)]
            for k in range(length):
                masks[i][k] += vector[k]
                masks[j][k] -= vector[k]
    return masks


def federated_train(client_rows, scaler_model, rounds=25, local_epochs=1, lr=0.05, seed=0, log=None):
    """Single-process FedAvg simulation with illustrative masks. client_rows: list of scaled (z, y) lists per client."""
    global_model = Softmax()
    global_model.mean, global_model.std = scaler_model.mean, scaler_model.std
    total = sum(len(rows) for rows in client_rows)
    width = len(global_model.flat())
    for r in range(rounds):
        masks = pairwise_masks(len(client_rows), width, f"{seed}-{r}")
        aggregate = [0.0] * width
        sample_masked = None
        for index, rows in enumerate(client_rows):
            local = Softmax()
            local.load_flat(global_model.flat())
            local.sgd(rows, epochs=local_epochs, lr=lr, seed=seed * 1000 + r * 50 + index, start_epoch=r)
            weight = len(rows) / total
            update = [weight * value for value in local.flat()]
            masked = [u + m for u, m in zip(update, masks[index])]  # simulated aggregate input; this process also holds the raw synthetic data
            if index == 0:
                sample_masked = (update[:4], masked[:4])
            aggregate = [a + b for a, b in zip(aggregate, masked)]
        global_model.load_flat(aggregate)  # masks cancel exactly in the sum
        if log is not None:
            log.append({"round": r + 1, "client0_true_update_head": [round(v, 4) for v in sample_masked[0]],
                        "client0_masked_update_head": [round(v, 2) for v in sample_masked[1]]})
    return global_model


def evaluate(model, rows, delays):
    """Log loss, accuracy, MAE of expected delay, and AUC for 'more than 7 days late'."""
    loss, correct, errors, scores = 0.0, 0, [], []
    for (z, y), delay in zip(rows, delays):
        probs = model.proba_scaled(z)
        loss -= math.log(max(probs[y], 1e-9))
        correct += max(range(len(probs)), key=probs.__getitem__) == y
        errors.append(abs(model.expected_delay(probs) - delay))
        scores.append((sum(probs[2:]), delay > 7))
    return {"log_loss": round(loss / len(rows), 4), "accuracy": round(correct / len(rows), 4),
            "mae_days": round(statistics.fmean(errors), 2), "auc_late_over_7d": auc(scores), "n": len(rows)}


def auc(pairs):
    positives = [score for score, label in pairs if label]
    negatives = [score for score, label in pairs if not label]
    if not positives or not negatives:
        return None
    ranked = sorted(pairs, key=lambda item: item[0])
    rank_sum, i = 0.0, 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        average = (i + j) / 2 + 1
        rank_sum += average * sum(1 for k in range(i, j + 1) if ranked[k][1])
        i = j + 1
    return round((rank_sum - len(positives) * (len(positives) + 1) / 2) / (len(positives) * len(negatives)), 4)


def load(path):
    with open(path) as handle:
        return Softmax.from_json(json.load(handle))


def predict_for(model, history_rows, amount, terms, due, portfolio_mean):
    """history_rows: [{'delay','amount','paid_date'}] for the customer; due: date."""
    x = features(history_rows, {"amount": amount, "terms": terms, "due_date": due}, portfolio_mean)
    probs = model.proba(x)
    return {"probabilities": [round(p, 4) for p in probs], "expected_delay_days": round(model.expected_delay(probs), 1),
            "p_late_over_7d": round(sum(probs[2:]), 4)}


def as_date(value):
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
