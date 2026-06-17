# Natural-Gas-Storage-Pricing-Model-Valuation-Engine
A quantitative research and production-prototype tool built for commodity trading desks. This application combines a non-linear regression engine (Trend + Seasonality) to interpolate and extrapolate continuous natural gas spot prices with a strict physical-asset ledger to value multi-transaction storage contracts.
## System Architecture Workflow

The dashboard handles data ingestion, parameter mapping, safety checks, and cash flow calculations in the following chronological sequence:

```mermaid
graph TD
    A[Start Dashboard] --> B(Load Nat_Gas.csv)
    B --> C(Fit Continuous Regression Curve)
    C --> D[User Inputs Custom Schedules]
    D --> E(Sort Transactions Chronologically)
    E --> F{Process Next Transaction}
    F -->|Injection| G{Exceeds Max Capacity?}
    G -->|Yes| H[Return Error Component]
    G -->|No| I(Update Inventory & Costs)
    F -->|Withdrawal| J{Exceeds Current Stock?}
    J -->|Yes| K[Return Error Component]
    J -->|No| L(Update Inventory & Revenue)
    I --> M{More Txs?}
    L --> M{More Txs?}
    M -->|Yes| F
    M -->|No| N(Calculate EOM Monthly Rental Fees)
    N --> O(Aggregate Trading Margin & Fees)
    O --> P[Output Net Contract Value & Audit Trail]
