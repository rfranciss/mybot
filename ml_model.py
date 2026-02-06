import numpy as np
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler


class MLModel:
    """
    ML leve e rápido (online):
    - StandardScaler incremental (partial_fit)
    - SGDClassifier (log_loss)
    - predict_proba robusto (retorna prob de WIN)
    - mantém compatibilidade com bots antigos: train(X,y), partial_fit(X,y), predict_proba(X)

    Observação:
    - Features esperadas: array 1D (n_features,) ou 2D (1,n_features).
    - Este modelo é propositalmente simples para rodar liso em VPS/fraco.
    """
    def __init__(self, seed: int = 42, warmup: int = 30):
        self.scaler = StandardScaler(with_mean=True, with_std=True)
        self.model = SGDClassifier(
            loss="log_loss",
            learning_rate="optimal",
            alpha=1e-5,
            random_state=seed,
        )
        self.warmup = int(warmup)
        self._seen = 0
        self.is_fitted = False
        self._classes = np.array([0, 1], dtype=int)

    def _to_2d(self, X):
        X = np.asarray(X, dtype=float)
        if X.ndim == 1:
            X = X.reshape(1, -1)
        return X

    def partial_fit(self, X, y):
        X = self._to_2d(X)
        y = np.asarray(y, dtype=int).reshape(-1)

        # scaler incremental
        self.scaler.partial_fit(X)
        Xs = self.scaler.transform(X)

        if not self.is_fitted:
            self.model.partial_fit(Xs, y, classes=self._classes)
            self.is_fitted = True
        else:
            self.model.partial_fit(Xs, y)

        self._seen += len(y)
        return True

    def train(self, X, y):
        return self.partial_fit(X, [y] if np.isscalar(y) else y)

    def ready(self):
        return bool(self.is_fitted and self._seen >= self.warmup)

    def predict_proba(self, X):
        """
        Retorna probabilidade de WIN (classe 1) como float (0..1).
        Se não estiver pronto, retorna 0.5.
        """
        if not self.is_fitted:
            return 0.5

        X = self._to_2d(X)
        try:
            Xs = self.scaler.transform(X)
            proba = self.model.predict_proba(Xs)
            # proba shape: (n,2) [p0,p1]
            return float(proba[-1][1])
        except Exception:
            return 0.5
