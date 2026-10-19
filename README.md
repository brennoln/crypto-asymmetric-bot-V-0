# Asymmetric Momentum Engine (v0.2 - Alpha)

An asynchronous, event-driven quantitative trading engine engineered to harvest right-tail fat-tailed distributions in decentralized liquidity pools through dynamic microstructural filtering, statistical anomaly detection, and asymmetric execution.

> **Architecture Status & Release Notice (v0.2)**  
> Version **0.2** transitions the codebase from the initial proof-of-concept into a robust, event-driven execution framework featuring rolling time-series analytics, dynamic High-Water Mark trailing protection, multi-source pair discovery, and an asynchronous, WAL-enabled SQLite persistence engine.

---

## 📌 Quantitative Thesis & Convex Payoff Model

Standard curve-fitting models and supervised machine learning architectures (e.g., LSTMs, naive regression networks) applied to non-stationary decentralized exchange (DEX) pricing series suffer from severe in-sample memorization, high latency, and low signal-to-noise ratios (SNR).

Instead of attempting unfeasible point-price forecasting, this engine models the trading game as a **strictly asymmetric convex payoff structure**:

$$\mathbb{E}[\text{Return}] = p_{\text{loss}} \cdot (-C_{\text{stop}}) + p_{\text{flat}} \cdot (-\delta_{\text{friction}}) + \sum_{k=1}^{n} p_k \cdot R_k$$

Where:
* The system accepts and expects an empirical base-rate loss of $p_{\text{loss}} + p_{\text{flat}} \approx 85\text{--}90\%$, constrained to a strictly parameterized fixed unit allocation risk ($\$15.00$).
* **Positive Mathematical Expectancy ($\mathbb{E}[R] > 0$)** is achieved via convex right-tail realization ($2.0\times, 10.0\times, 30.0\times, 100.0\times$) captured during microstructural liquidity ignition events.

---

## 🔬 Core Microstructure & Quantitative Features (v0.2)

### 1. Multi-Source Discovery & Ignition Scoring
The engine polls multiple decentralized token discovery endpoints concurrently (`token-profiles`, `token-boosts/latest`, `token-boosts/top`), deduplicating ticker clones and ranking candidates via a composite **Ignition Score**:

$$\text{Score} = \left(\min\left(\frac{V_{5m}}{L_{\text{pool}}}, 3.0\right) \times 40\right) + \left(\min\left(\frac{V_{5m}}{\bar{V}_{h1}}, 5.0\right) \times 25\right) + (\max(\text{OFI}, 0) \times 25) + (\min(\text{Buys}, 100) \times 0.10)$$

* **Turnover Velocity ($V_{5m} / L_{\text{pool}}$):** Identifies anomalous volume relative to underlying liquidity depth.
* **Volume Acceleration ($V_{5m} / \bar{V}_{h1}$):** Gauges the burst factor over the 1-hour moving baseline.
* **Order Flow Imbalance (OFI):** Measures instantaneous taker aggression against passive pool inventory:
  $$\text{OFI} = \frac{\text{Buys}_{5m} - \text{Sells}_{5m}}{\text{Buys}_{5m} + \text{Sells}_{5m}} \in [-1, 1]$$

### 2. Real-Time Rolling Statistical Strategy
For active positions, incoming ticks populate an in-memory sliding window buffer computing rolling metrics:
* **Volume Z-Score:** $Z = \frac{V_{5m} - \mu_{V}}{\sigma_{V}}$ detecting statistical volume shocks ($Z \ge 1.2$).
* **Statistical Exhaustion Exits:** Early liquidation signals triggered when order flow violently flips to seller-dominated regimes ($\text{OFI} \le -0.35$).

### 3. Asymmetric Laddered Holding Map & Dynamic Protection
* **De-risking Ladder:**
  * **$2.0\times$ Multiplier:** Liquidates $50\%$ of original position inventory, retrieving $100\%$ of initial capital invested ($\Delta \text{Capital} = 0$, rendering the remaining balance strictly **Risk-Free**).
  * **$10.0\times$ Multiplier:** Liquidates $20\%$.
  * **$30.0\times$ Multiplier:** Liquidates $15\%$.
  * **$100.0\times$ Multiplier:** Liquidates final $15\%$ (*Moonbag* tail target).
* **High-Water Mark (Trailing Stop):** Activates once a position reaches $\ge +40\%$ gain ($\ge 1.40\times$). A subsequent $25\%$ retracement from the historic peak immediately triggers market liquidation to lock in net profit.
* **Anti-Wick Safeguard:** Prevents premature stop-out caused by ephemeral reporting anomalies or transient wicks when underlying pool liquidity remains intact.
* **Inertia Time-Stop:** Positions lingering flat with near-zero momentum past $6.0$ minutes are pruned at market value to free up portfolio capacity, unless already elevated to *Risk-Free* status ($2.0\times$) or floating with $> +20\%$ gain.

---

## 🏗 Modular Architecture

```text
crypto-asymmetric-bot/
├── analytics/
│   ├── analytics.py          # Vectorized rolling metrics (Z-Score, Volatility, OFI)
│   ├── report.py             # Quantitative performance summary (PnL, Win-Rate, Expectancy)
│   └── test_analytics.py     # Standalone diagnostic runner for historical tick metrics
├── config/
│   └── settings.py           # Pydantic-validated hyperparameters & network limits
├── data/
│   ├── database.py           # Async SQLite persistence (WAL mode) with lock timeouts
│   └── trading_history.db    # Relational store for high-frequency ticks and trades
├── src/
│   ├── audit/
│   │   └── holder_analyzer.py# Entry safety heuristics (pool age, volume, liquidity bands)
│   ├── execution/
│   │   └── paper_client.py   # High-fidelity Paper Trading OMS with lifecycle transitions
│   ├── risk/
│   │   └── position_sizer.py # Fixed unit sizing & daily portfolio drawdown circuit breaker
│   ├── scanner/
│   │   └── dex_scanner.py    # Multi-endpoint discovery, batch polling & ignition scoring
│   ├── strategy/
│   │   ├── holding_map.py    # Asymmetric laddered de-risking structure
│   │   └── stat_strategy.py  # Tick-driven signal generator (Z-score + OFI)
│   └── utils/
│       └── logger.py         # Structured asynchronous console logger
├── tests/                    # Comprehensive Pytest test suite (62 unit & integration tests)
├── main.py                   # Asyncio dual-loop orchestration (Scanner + Watcher)
├── pytest.ini                # Pytest configuration
├── requirements.txt          # Python dependency specifications
└── .env.example              # Environment variables template
```

---

## ⚡ Getting Started

### 1. Prerequisites & Installation

Clone the repository and install dependencies:

```bash
git clone https://github.com/brennoln/crypto-asymmetric-bot-V-0.git
cd crypto-asymmetric-bot
python -m pip install -r requirements.txt
```

### 2. Configuration

Copy the sample environment file to override default settings:

```bash
cp .env.example .env
```

Key hyperparameters available in `config/settings.py` / `.env`:
* `POSITION_SIZE_USD`: Fixed USD allocation per trade (default: `$15.00`).
* `MAX_ACTIVE_POSITIONS`: Maximum simultaneous portfolio slots (default: `10`).
* `MAX_DAILY_LOSS_USD`: Portfolio circuit breaker tripping threshold (default: `$100.00`).
* `MIN_POOL_AGE_MINUTES` / `MAX_POOL_AGE_HOURS`: Anti-sniper and maturity window (default: `15m` to `8h`).
* `HARD_STOP_LOSS_PCT`: Catastrophic invalidation stop (default: `35%`).

### 3. Execution

Launch the engine in asynchronous paper-trading mode:

```bash
python main.py
```

### 4. Quantitative Analytics & Inspection

Inspect real-time portfolio performance, realized PnL, and closed trade statistics at any time:

```bash
python analytics/report.py
```

Inspect tick statistics and strategy decision logs from the local database:

```bash
python analytics/test_analytics.py
python src/strategy/test_strategy.py
```

---

## 🧪 Test Suite

The repository includes a comprehensive `pytest` test suite covering 100% of the core quantitative logic, database transactions, execution transitions, and safety filters:

```bash
python -m pytest
```

```text
============================= 62 passed in 7.45s ==============================
```

---

## 🛣 Quantitative Roadmap (v0.3+)

- [ ] **Mempool & Pending Liquidity Tracking:** Real-time WebSocket listener for pending DEX liquidity operations.
- [ ] **Jump-Diffusion & Hawkes Processes:** Modeling self-exciting transaction clustering in high-turnover pools.
- [ ] **On-Chain Solana / EVM Execution Drivers:** Low-latency RPC submission routing via private builders (Jito / Flashbots).
- [ ] **Dynamic Kelly Sizing:** Transition from fixed-unit sizing to fractional Kelly Criterion parameterized by rolling win/loss distributions.
