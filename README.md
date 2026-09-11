# Asymmetric Momentum Engine (AME)

An event-driven algorithmic trading engine designed to capture high-convexity, fat-tail return distributions in decentralized micro-cap liquidity pools.

## 📌 Quantitative Rationale & Thesis

Rather than predicting future prices through curve-fitting models (such as LSTMs or standard moving averages over noisy time series), this engine operates on an **asymmetric payoff structure**:

$$\mathbb{E}[\text{Return}] = p_{\text{loss}} \cdot (-1.0) + p_{\text{flat}} \cdot (-\delta) + p_{\text{tail}} \cdot (R_{\text{asymmetric}})$$

Where the system accepts a high rate of early cut-offs ($p_{\text{loss}} + p_{\text{flat}} \approx 85\text{--}90\%$) constrained to a small, fixed unit risk ($\$15.00$), while exploiting momentum ignition and order flow imbalances targeting multi-stage laddered exits ($2\times, 10\times, 30\times, 100\times$).

### Key Features:
- **Microstructure Filtering:** Discards assets based on buy/sell transaction ratios ($> 1.35$), short-term momentum spikes ($V_{5m}$), and pool liquidity boundaries.
- **Dynamic Portfolio Management:** Strict slot capacity constraints (`MAX_ACTIVE_POSITIONS = 10`) paired with time-decay stops (stagnant asset liquidation after 6 minutes).
- **Asymmetric Holding Map:** Automated capital de-risking: liquidates $50\%$ of the initial position at $2.0\times$ entry price, making the remaining position risk-free.
- **Asynchronous Batch Execution:** Concurrent multi-token monitoring using vectorized REST batch requests to DexScreener endpoints, reducing network I/O overhead.

---

## 🏗 System Architecture

```text
crypto-asymmetric-bot/
├── config/             # Pydantic environment validation and hyper-parameters
├── src/
│   ├── scanner/        # DEX discovery engine (concurrent pair polling)
│   ├── audit/          # On-chain liquidity and safety heuristics
│   ├── strategy/       # Convex laddered Holding Map logic
│   ├── execution/      # Paper trading OMS and market liquidation routines
│   ├── risk/           # Capital allocation and position sizing engine
│   └── utils/          # Structured logging and formatters
├── main.py             # Event-driven asynchronous runtime
└── requirements.txt