from dataclasses import dataclass

@dataclass
class HoldingTarget:
    multiplier: float       # Alvo de valorização
    sell_percent: float     # % da posição original a ser vendida

class HoldingMap:
    def __init__(self):
        self.targets = [
            HoldingTarget(multiplier=2.0, sell_percent=0.50),   # Tira o capital inicial: operação vira Risk-Free
            HoldingTarget(multiplier=10.0, sell_percent=0.20),  # Realiza lucro expressivo no bolso
            HoldingTarget(multiplier=30.0, sell_percent=0.15),  # Captura a explosão intermediária
            HoldingTarget(multiplier=100.0, sell_percent=0.15)  # Moonbag final (alvo assimétrico)
        ]

    def evaluate_exit(self, entry_price: float, current_price: float) -> list[str]:
        if entry_price <= 0:
            return []
        
        ratio = current_price / entry_price
        actions = []
        for target in self.targets:
            if ratio >= target.multiplier:
                actions.append(f"Gatilho {target.multiplier}x atingido: Vender {target.sell_percent * 100}%")
        return actions