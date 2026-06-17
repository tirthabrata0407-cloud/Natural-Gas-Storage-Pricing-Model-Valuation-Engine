import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from datetime import datetime, date

# ==========================================
# 1. PAGE SETUP & CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="Natural Gas Storage Valuation Dashboard", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⛽ Natural Gas Storage Pricing Model & Valuation Engine")
st.markdown("""
This production prototype integrates a **continuous trend-plus-seasonality regression model** with a **multi-transaction physical contract pricing engine** to value long-term storage agreements.
""")

# ==========================================
# 2. CORE MATHEMATICAL MODEL (CACHED)
# ==========================================
@st.cache_data
def load_and_fit_base_model():
    # Load dataset
    df = pd.read_csv('Nat_Gas.csv')
    df['Dates'] = pd.to_datetime(df['Dates'])
    df['Prices'] = df['Prices'].astype(float)
    
    start_date = df['Dates'].min()
    df['Days'] = (df['Dates'] - start_date).dt.days
    
    # Mathematical Model: Linear Trend + Sinusoidal Annual Seasonality
    def gas_price_model(t, intercept, slope, amplitude, phase):
        omega = 2 * np.pi / 365.25
        return intercept + slope * t + amplitude * np.sin(omega * t + phase)
    
    # Fit parameters via non-linear least squares regression
    popt, _ = curve_fit(gas_price_model, df['Days'], df['Prices'], p0=[10, 0.001, 1, 0])
    return df, start_date, gas_price_model, popt

try:
    df, start_date, gas_price_model, popt = load_and_fit_base_model()
    intercept_opt, slope_opt, amp_opt, phase_opt = popt
except FileNotFoundError:
    st.error("❌ 'Nat_Gas.csv' not found. Please ensure it is located in the same directory as this script.")
    st.stop()

def get_market_price(date_input):
    """Calculates continuous predicted natural gas price for any date."""
    dt = pd.to_datetime(date_input)
    days_diff = (dt - start_date).days
    return gas_price_model(days_diff, *popt)

# ==========================================
# 3. CONTRACT PRICING ENGINE
# ==========================================
def price_storage_contract(injections, withdrawals, inj_fee, wit_fee, max_cap, storage_rate):
    """Processes chronological transactional ledger and assesses storage costs & cash flows."""
    actions = []
    for tx in injections:
        if tx['volume'] > 0:
            actions.append({'date': pd.to_datetime(tx['date']), 'type': 'injection', 'volume': tx['volume']})
    for tx in withdrawals:
        if tx['volume'] > 0:
            actions.append({'date': pd.to_datetime(tx['date']), 'type': 'withdrawal', 'volume': tx['volume']})
            
    # Sort everything strictly by chronological order
    actions = sorted(actions, key=lambda x: x['date'])
    
    if not actions:
        return {"status": "Empty", "message": "No active schedules populated yet."}
        
    current_inventory = 0.0
    total_inj_cost = 0.0
    total_wit_rev = 0.0
    total_op_fees = 0.0
    timeline_records = []
    ledger_details = []
    
    for act in actions:
        dt = act['date']
        vol = act['volume']
        mkt_price = get_market_price(dt)
        
        if act['type'] == 'injection':
            if current_inventory + vol > max_cap:
                return {"status": "Error", "message": f"❌ Operational Breach: Injection on {dt.strftime('%Y-%m-%d')} exceeds maximum storage threshold ({max_cap} units)."}
            current_inventory += vol
            cash_flow = -1 * (vol * mkt_price)
            fee = vol * inj_fee
            total_inj_cost += (vol * mkt_price)
            total_op_fees += fee
            
        elif act['type'] == 'withdrawal':
            if current_inventory - vol < 0:
                return {"status": "Error", "message": f"❌ Inventory Shortfall: Attempted withdrawal on {dt.strftime('%Y-%m-%d')} exceeds total physical stock available ({current_inventory:.1f} units)."}
            current_inventory -= vol
            cash_flow = vol * mkt_price
            fee = vol * wit_fee
            total_wit_rev += cash_flow
            total_op_fees += fee
            
        total_fees = fee
        net_tx_pnl = cash_flow - total_fees
        
        ledger_details.append({
            "Date": dt.strftime('%Y-%m-%d'),
            "Action": act['type'].upper(),
            "Volume (Units)": vol,
            "Est. Market Price": f"${mkt_price:.2f}",
            "Gross Cash Flow": f"${cash_flow:,.2f}",
            "Op Fee Paid": f"${fee:,.2f}",
            "Post-Tx Inventory": round(current_inventory, 2)
        })
        
        timeline_records.append({'date': dt, 'inventory_after_tx': current_inventory})

    # Calculate Continuous Monthly Storage Rental Costs
    start_contract, end_contract = actions[0]['date'], actions[-1]['date']
    months_range = pd.date_range(start=start_contract.strftime('%Y-%m-01'), end=end_contract.strftime('%Y-%m-%d'), freq='MS')
    
    total_storage_rental = 0.0
    for m in months_range:
        month_end = m + pd.DateOffset(months=1) - pd.DateOffset(days=1)
        past_txs = [r['inventory_after_tx'] for r in timeline_records if r['date'] <= month_end]
        inv_at_month_end = past_txs[-1] if past_txs else 0.0
        total_storage_rental += (inv_at_month_end * storage_rate)
        
    gross_margin = total_wit_rev - total_inj_cost
    net_value = gross_margin - total_op_fees - total_storage_rental
    
    return {
        "status": "Success",
        "gross_margin": gross_margin,
        "op_fees": total_op_fees,
        "rental_fees": total_storage_rental,
        "net_value": net_value,
        "final_inventory": current_inventory,
        "ledger": pd.DataFrame(ledger_details)
    }

# ==========================================
# 4. SIDEBAR CONTROLS: FIXED FEES & LIMITS
# ==========================================
st.sidebar.header("🛡️ Facility Parameters & Fees")
max_capacity = st.sidebar.number_input("Max Storage Capacity (Units)", value=15000, step=1000)
inj_fee_rate = st.sidebar.number_input("Injection Fee Rate ($/Unit)", value=0.02, step=0.01, format="%.3f")
wit_fee_rate = st.sidebar.number_input("Withdrawal Fee Rate ($/Unit)", value=0.03, step=0.01, format="%.3f")
monthly_rental_rate = st.sidebar.number_input("Monthly Storage Rate ($/Unit Held)", value=0.010, step=0.005, format="%.3f")

st.sidebar.markdown("---")
st.sidebar.subheader("📈 Underlying Model Constants")
st.sidebar.text(f"Base Price (Intercept): ${intercept_opt:.2f}")
st.sidebar.text(f"Seasonal Volatility (Amp): ${abs(amp_opt):.2f}")
st.sidebar.text(f"Daily Structural Drift (Slope): ${slope_opt:.5f}")

# ==========================================
# 5. MAIN CONTENT AREA: TAB LAYOUT
# ==========================================
tab1, tab2 = st.tabs(["📋 Contract Structuring Engine", "📊 Model Visualizations & Forecasts"])

with tab1:
    st.subheader("🛠️ Step 1: Customize Client Transaction Schedules")
    st.caption("Traders can input custom volumes and target execution dates for up to 3 distinct operations below.")
    
    col_inj, col_wit = st.columns(2)
    
    # Collect up to 3 discrete Injection actions
    with col_inj:
        st.markdown("**📥 Injection Window Schedule (Buys)**")
        inj_schedule = []
        for i in range(1, 4):
            c1, c2 = st.columns([1.2, 1])
            with c1:
                d = st.date_input(f"Inj Date #{i}", value=date(2023, 5 + i, 15), key=f"inj_d_{i}")
            with c2:
                v = st.number_input(f"Inj Vol #{i}", value=5000 if i <= 2 else 0, step=1000, key=f"inj_v_{i}")
            inj_schedule.append({'date': d, 'volume': v})

    # Collect up to 3 discrete Withdrawal actions
    with col_wit:
        st.markdown("**📤 Withdrawal Window Schedule (Sells)**")
        wit_schedule = []
        for i in range(1, 4):
            c1, c2 = st.columns([1.2, 1])
            with c1:
                d = st.date_input(f"Wit Date #{i}", value=date(2023, 11 + i, 15), key=f"wit_d_{i}")
            with c2:
                v = st.number_input(f"Wit Vol #{i}", value=5000 if i <= 2 else 0, step=1000, key=f"wit_v_{i}")
            wit_schedule.append({'date': d, 'volume': v})

    # Execute Pricing Model Valuation
    st.markdown("---")
    st.subheader("💰 Step 2: Contract Financial Evaluation")
    
    valuation = price_storage_contract(
        inj_schedule, wit_schedule, 
        inj_fee_rate, wit_fee_rate, 
        max_capacity, monthly_rental_rate
    )
    
    if valuation["status"] == "Empty":
        st.warning(valuation["message"])
        
    elif valuation["status"] == "Error":
        st.error(valuation["message"])
        
    elif valuation["status"] == "Success":
        # Metric Layout Card Component
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Gross Trading Spread", f"${valuation['gross_margin']:,.2f}")
        m2.metric("Total Exec Ops Fees", f"-${valuation['op_fees']:,.2f}")
        m3.metric("Total Facility Lease Costs", f"-${valuation['rental_fees']:,.2f}")
        
        # Color code final value to signify profit/loss metrics
        final_pnl = valuation['net_value']
        m4.metric(
            label="Net Contract Fair Value", 
            value=f"${final_pnl:,.2f}", 
            delta=f"${final_pnl:,.2f}" if final_pnl >= 0 else f"-${abs(final_pnl):,.2f}",
            delta_color="normal" if final_pnl >= 0 else "inverse"
        )
        
        if valuation['final_inventory'] > 0:
            st.warning(f"⚠️ Inventory Warning: At expiration, the client is leaving **{valuation['final_inventory']:,} units** abandoned in storage.")
        
        # Output Structured Log Table
        st.markdown("#### 📑 Order Execution Audit Trail")
        st.dataframe(valuation['ledger'], use_container_width=True)

with tab2:
    st.subheader("📉 Pricing Curve & Trend Forecast Analytics")
    
    # Calculate boundaries (Extend graph to hold 1-year forward extrapolation)
    max_hist_date = df['Dates'].max()
    extended_end_date = max_hist_date + pd.DateOffset(years=1)
    
    # Generate daily visualization spacing
    visual_dates = pd.date_range(start=start_date, end=extended_end_date, freq='D')
    visual_days = (visual_dates - start_date).days
    modeled_prices = gas_price_model(visual_days, *popt)
    
    # Generate Matplotlib figure object
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.scatter(df['Dates'], df['Prices'], color='red', s=45, zorder=5, label='Historical Monthly Snapshot')
    ax.plot(visual_dates, modeled_prices, color='#1f77b4', linewidth=2, label='Continuous Fitting/Extrapolation Curve')
    
    # Add an overlapping marker for active deal dates if present
    if valuation["status"] == "Success":
        all_tx_dates = [pd.to_datetime(tx['date']) for tx in inj_schedule + wit_schedule if tx['volume'] > 0]
        all_tx_prices = [get_market_price(d) for d in all_tx_dates]
        ax.scatter(all_tx_dates, all_tx_prices, color='orange', marker='X', s=120, zorder=6, label='Deal Execution Points')
        
    ax.axvline(x=max_hist_date, color='gray', linestyle='--', alpha=0.6)
    ax.text(max_hist_date + pd.DateOffset(days=12), df['Prices'].min(), 'Extrapolation Zone →', color='gray', fontsize=10, weight='bold')
    
    ax.set_xlabel('Timeline Horizon')
    ax.set_ylabel('Commodity Price ($)')
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.2)
    
    st.pyplot(fig)
    
    # Interactive Individual Pricing Calculator Component
    st.markdown("---")
    st.markdown("#### 🔍 Spot Ad-Hoc Quotation Calculator")
    c_calc1, c_calc2 = st.columns([1, 2])
    with c_calc1:
        check_date = st.date_input("Select Target Query Date", value=max_hist_date.date() + pd.DateOffset(months=3))
    with c_calc2:
        estimated_spot = get_market_price(check_date)
        is_future = pd.to_datetime(check_date) > max_hist_date
        st.metric(
            label=f"Continuous Price Estimate ({'Extrapolated Future' if is_future else 'In-Sample Interpolation'})",
            value=f"${estimated_spot:.3f} per unit"
        )