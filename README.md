# Asymmetric Momentum Engine (v0.1 - PoC)

An asynchronous, event-driven quantitative prototype designed to capture fat-tail return distributions in decentralized liquidity pools through dynamic order flow filtering and microstructural momentum.

> **Research Status & Roadmap Notice**  
> This repository represents the initial architectural proof-of-concept (**v0.1**) for a comprehensive, production-grade platform dedicated to high-frequency mapping and algorithmic execution. The long-term system will incorporate stochastic calculus (Ornstein-Uhlenbeck processes, Hawkes processes for jump-diffusion clustering) and real-time on-chain mempool analytics.

---

## 📌 Quantitative Rationale & Convex Payoff Thesis

Traditional curve-fitting architectures (e.g., LSTMs, naive multi-layer perceptrons) applied to non-stationary financial price series often succumb to low signal-to-noise ratio (SNR) and severe in-sample memorization. 

Instead of attempting point-price forecasting, this engine models the trading game as an **asymmetric payoff structure**:

$$\mathbb{E}[\text{Return}] = p_{\text{loss}} \cdot (-C_{\text{stop}}) + p_{\text{flat}} \cdot (-\delta_{\text{friction}}) + \sum_{k=1}^{n} p_k \cdot R_k$$

Where:
* The system expects and accepts an empirical baseline loss rate of $p_{\text{loss}} + p_{\text{flat}} \approx 85\text{--}90\%$, constrained to a fixed unit bet risk ($\$15.00$).
* **Positive Expectancy ($\mathbb{E}[R] > 0$)** is achieved not via high win rate, but through convex right-tail realization ($2\times, 10\times, 30\times, 100\times$) captured during short-lived liquidity ignition events.

---

## 🔬 Microstructure Filters & Safeguards

The engine mitigates structural decentralized exchange (DEX) risks prior to capital commitment:

* **Order Flow Imbalance (OFI):** Imposes a dynamic buy/sell volume threshold ($\text{Ratio}_{5m} \ge 1.35$) to verify organic taker aggression versus passive exit liquidity.
* **Volume-to-Liquidity Acceleration:** Monitors short-window volume velocity ($V_{5m}$) relative to total pool depth ($L_{\text{pool}}$).
* **Time-Decay Liquidation (Inertia Stop):** Flat price action is penalized. Assets exhibiting near-zero volatility over 6 minutes are liquidated at market rate to liberate capital slots for active momentum regimes.
* **Asymmetric Holding Map (Laddered De-risking):** Liquidates $50\%$ of original inventory at $2.0\times$, rendering the remaining position strictly *risk-free* ($\Delta \text{Capital} = 0$) while letting the runner target high-order multiples.

---

## 🏗 Modular Architecture

The repository enforces decoupled service separation to allow independent unit testing, strategy extension, and exchange abstraction:

```text
crypto-asymmetric-bot/
├── config/
│   └── settings.py           # Pydantic-validated hyperparameters & network limits
├── src/
│   ├── scanner/              # DEX pair discovery & parallel REST/WS polling
│   ├── audit/                # On-chain safety heuristics & holder analysis
│   ├── strategy/             # Convex laddered Holding Map logic
│   ├── execution/            # Paper-trading OMS & real-time market liquidation
│   ├── risk/                 # Portfolio slot allocation & loss guardrails
│   └── utils/                # Structured asynchronous logging
├── main.py                   # Asyncio event loop orchestration
└── requirements.txt