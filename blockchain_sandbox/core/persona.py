from dataclasses import dataclass


@dataclass(frozen=True)
class MinerPersona:
    """
    Lightweight personality profile for non-rational strategic drift.
    All scores are in [0, 1].
    """

    name: str
    risk_appetite: float
    aggression: float
    patience: float
    sociability: float
    investment_style: str
    narrative_style: str

