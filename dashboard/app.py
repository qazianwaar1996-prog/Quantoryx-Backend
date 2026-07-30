# dashboard/app.py

import os
import sys

import pandas as pd
import streamlit as st

# Ensure the project root is importable when Streamlit runs this file directly.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from utils.path_manager import PathManager  # noqa: E402


# Page Config
st.set_page_config(
    page_title="Quantoryx Analytics Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title & Refresh Banner
st.title("📊 Quantoryx - Autonomous Mission Control")
st.caption("Local Real-Time Quantitative Analytics & Decision Trace Ledger")

# Define canonical data paths (single source of truth via PathManager).
# Fall back to legacy root-level files if a canonical report is absent, so
# older sessions still render.
def _resolve(category: str, filename: str) -> str:
    canonical = PathManager.resolve_path(category, filename)
    return canonical if os.path.exists(canonical) else filename


PORTFOLIO_PATH = _resolve("reports", "portfolio_report.csv")
TRADE_LOG_PATH = _resolve("trades", "paper_trade_log.csv")
AI_LOG_PATH = _resolve("logs", "ai_decision_log.csv")
WALK_FORWARD_PATH = _resolve("reports", "walk_forward_report.csv")


def load_csv_safely(file_path: str) -> pd.DataFrame:
    """
    Loads and checks local CSV reports, returning an empty DataFrame if missing.
    """
    if os.path.exists(file_path):
        try:
            return pd.read_csv(file_path)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


# Load Dataframes
df_portfolio = load_csv_safely(PORTFOLIO_PATH)
df_trades = load_csv_safely(TRADE_LOG_PATH)
df_ai = load_csv_safely(AI_LOG_PATH)
df_wf = load_csv_safely(WALK_FORWARD_PATH)

# Check for Empty States
if df_portfolio.empty and df_trades.empty and df_ai.empty:
    st.warning("⚠️ No active session files detected. Run the main pipeline first to compile database records.")
    st.code("python run_quantoryx.py --symbol EURUSD --timeframe 1H")
    st.stop()

# --- SIDEBAR: MISSION CONTROL ---
st.sidebar.header("🕹️ System Controls")
st.sidebar.write("Local Dashboard Parameters")

# Display Active Market Setup
if not df_portfolio.empty and not df_ai.empty:
    latest_ai = df_ai.iloc[-1] if not df_ai.empty else None
    
    st.sidebar.subheader("🟢 Active Session")
    st.sidebar.metric("Symbol", str(latest_ai.get("symbol", "N/A")) if latest_ai is not None else "N/A")
    st.sidebar.metric("Timeframe", str(latest_ai.get("timeframe", "N/A")) if latest_ai is not None else "N/A")

st.sidebar.markdown("---")
st.sidebar.info(
    "💡 **Auto-Refresh**\n"
    "The dashboard loads local CSV files. After running a new backtest or "
    "paper trading cycle, click the **Rerun** button in the top right corner to sync data."
)

# --- SECTION 1: AI CHAMPION INSIGHTS & REGIME PROFILE ---
st.write("### 🤖 Cognitive AI Selection Profile")

if not df_ai.empty:
    latest_ai = df_ai.iloc[-1]
    col_ai1, col_ai2, col_ai3, col_ai4 = st.columns(4)
    
    with col_ai1:
        st.metric("Champion Model", str(latest_ai.get("selected_strategy", "N/A")).upper())
    with col_ai2:
        st.metric("AI Confidence Score", f"{float(latest_ai.get('confidence_score', 0.0)):.1f} / 100")
    with col_ai3:
        st.metric("Market Regime Context", str(latest_ai.get("market_regime", "N/A")))
    with col_ai4:
        st.metric("AI Status", str(latest_ai.get("decision_action", "N/A")))
        
    st.info(f"📝 **AI Decision Explanation:**\n{latest_ai.get('explanation', 'No explanation logged.')}")
else:
    st.write("No active AI log trace found.")

# --- SECTION 2: PORTFOLIO PERFORMANCE METRICS ---
st.write("### 📈 Portfolio Performance Indicators")

if not df_portfolio.empty:
    # Compile portfolio statistics
    start_bal = float(df_portfolio['balance'].iloc[0])
    current_eq = float(df_portfolio['equity'].iloc[-1])
    total_pnl = current_eq - start_bal
    return_pct = (total_pnl / start_bal) * 100.0 if start_bal else 0.0
    # Derive drawdown defensively if the column is absent in a legacy file.
    if 'drawdown_pct' not in df_portfolio.columns:
        peak = df_portfolio['equity'].cummax()
        df_portfolio['drawdown_pct'] = ((peak - df_portfolio['equity']) / peak * 100.0).fillna(0.0)
    max_dd = float(df_portfolio['drawdown_pct'].max())
    
    # Calculate win rate and profit factor if trade logs exist
    win_rate = 0.0
    profit_factor = 1.0
    total_trades = 0
    
    if not df_trades.empty:
        total_trades = len(df_trades)
        wins = df_trades[df_trades['pnl'] > 0]['pnl']
        losses = df_trades[df_trades['pnl'] < 0]['pnl']
        
        win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
        gross_profit = wins.sum()
        gross_loss = abs(losses.sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 1.0)

    # Display metric cards
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Current Equity", f"${current_eq:,.2f}", f"{return_pct:+.2f}%")
    with col2:
        st.metric("Total Net P/L", f"${total_pnl:+,.2f}")
    with col3:
        st.metric("Max Peak Drawdown", f"{max_dd:.2f}%")
    with col4:
        st.metric("Win Rate", f"{win_rate:.2f}%", f"{total_trades} Trades")
    with col5:
        st.metric("Profit Factor", f"{profit_factor:.2f}")

    # --- SECTION 3: CHARTS PANEL ---
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.write("#### Capital Performance (Equity Curve)")
        df_chart = df_portfolio.copy()
        if 'date' in df_chart.columns:
            df_chart.set_index('date', inplace=True)
        st.line_chart(df_chart[['balance', 'equity']])
        
    with chart_col2:
        st.write("#### Account Drawdown Curve (%)")
        st.area_chart(df_portfolio['drawdown_pct'])
else:
    st.write("No active equity or balance history logs detected.")

# --- SECTION 4: STRATEGY LEADERBOARDS & TRADE LOGS ---
tab1, tab2, tab3 = st.tabs(["📊 Optimization & WFV", "📜 Executed Trades Log", "🤖 Full Decision Trace Logs"])

with tab1:
    st.write("#### Walk-Forward Strategy Selection Rankings")
    if not df_wf.empty:
        st.dataframe(df_wf, use_container_width=True)
    else:
        st.info("No Walk-Forward validation records detected in this directory.")

with tab2:
    st.write("#### Recent Paper Trades Log")
    if not df_trades.empty:
        st.dataframe(df_trades.iloc[::-1], use_container_width=True)
    else:
        st.info("No active virtual trades have executed during this session.")

with tab3:
    st.write("#### Historical AI Decision & Explication Engine Logs")
    if not df_ai.empty:
        st.dataframe(df_ai.iloc[::-1], use_container_width=True)
    else:
        st.info("No historical AI decision trace records found.")
