# market_regime/detector.py

import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple


class MarketRegimeDetector:
    """
    Classifies market conditions into Trending, Ranging, High Volatility,
    and Low Volatility regimes using standard quantitative indicators.
    """
    def __init__(
        self,
        ema_period: int = 50,
        slope_lookback: int = 5,
        adx_period: int = 14,
        atr_period: int = 14,
        bb_period: int = 20,
        bb_std: float = 2.0,
        volatility_percentile_period: int = 100,
        trend_threshold: float = 25.0,  # ADX > 25 indicates strong trend
        range_threshold: float = 20.0,  # ADX < 20 indicates weak or ranging trend
    ):
        self.ema_period = ema_period
        self.slope_lookback = slope_lookback
        self.adx_period = adx_period
        self.atr_period = atr_period
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.volatility_percentile_period = volatility_percentile_period
        self.trend_threshold = trend_threshold
        self.range_threshold = range_threshold

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates ADX, ATR, EMA Slope, and Bollinger Band Width using standard pandas.
        """
        # Work on a copy to avoid SettingWithCopyWarnings
        data = df.copy()
        
        # 1. EMA & Slope
        data['ema'] = data['close'].ewm(span=self.ema_period, adjust=False).mean()
        # Slope as percentage change of the EMA over the lookback window
        data['ema_slope'] = data['ema'].pct_change(periods=self.slope_lookback) * 100

        # 2. Average True Range (ATR)
        high_low = data['high'] - data['low']
        high_close_prev = (data['high'] - data['close'].shift(1)).abs()
        low_close_prev = (data['low'] - data['close'].shift(1)).abs()
        
        tr = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
        # Standard wilder's smoothing style approximation via EMA
        data['atr'] = tr.ewm(alpha=1/self.atr_period, adjust=False).mean()
        # Normalize ATR by price to make it scale-invariant
        data['atr_pct'] = data['atr'] / data['close'] * 100

        # 3. Bollinger Bands & Band Width
        bb_middle = data['close'].rolling(window=self.bb_period).mean()
        bb_std_dev = data['close'].rolling(window=self.bb_period).std()
        bb_upper = bb_middle + (self.bb_std * bb_std_dev)
        bb_lower = bb_middle - (self.bb_std * bb_std_dev)
        
        # Avoid division by zero on flat/identical data
        data['bb_width'] = np.where(
            bb_middle != 0, 
            (bb_upper - bb_lower) / bb_middle * 100, 
            0.0
        )

        # 4. Average Directional Index (ADX)
        up_move = data['high'] - data['high'].shift(1)
        down_move = data['low'].shift(1) - data['low']
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        
        # Smooth DM using Wilder's EMA equivalent technique
        smooth_tr = tr.ewm(alpha=1/self.adx_period, adjust=False).mean()
        smooth_plus_dm = pd.Series(plus_dm, index=data.index).ewm(alpha=1/self.adx_period, adjust=False).mean()
        smooth_minus_dm = pd.Series(minus_dm, index=data.index).ewm(alpha=1/self.adx_period, adjust=False).mean()
        
        # Avoid division by zero
        plus_di = np.where(smooth_tr != 0, 100 * (smooth_plus_dm / smooth_tr), 0.0)
        minus_di = np.where(smooth_tr != 0, 100 * (smooth_minus_dm / smooth_tr), 0.0)
        
        di_sum = plus_di + minus_di
        di_diff = np.abs(plus_di - minus_di)

        # Guard against divide-by-zero on flat segments (suppress the transient
        # NaN warning; the np.where already selects a safe 0.0 fallback).
        with np.errstate(divide="ignore", invalid="ignore"):
            dx = np.where(di_sum != 0, 100 * (di_diff / di_sum), 0.0)
        data['adx'] = pd.Series(dx, index=data.index).ewm(alpha=1/self.adx_period, adjust=False).mean()

        # 5. Volatility Baselines (Rolling percentiles or averages)
        # We classify high/low relative to the asset's rolling window baseline
        data['bb_width_median'] = data['bb_width'].rolling(window=self.volatility_percentile_period).median()
        data['atr_pct_median'] = data['atr_pct'].rolling(window=self.volatility_percentile_period).median()

        return data

    def classify_regimes(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classifies each row into discrete market regimes based on indicator thresholds.
        """
        data = self.calculate_indicators(df)
        
        # Initialize regime column holders
        trend_regimes = []
        volatility_regimes = []
        combined_regimes = []

        # Iterate over the rows to apply state rules safely
        # It's faster to compute using vector logic but loops are explicit and robust for edge cases.
        for idx, row in data.iterrows():
            # Check for sufficient indicator warmup period
            if pd.isna(row['adx']) or pd.isna(row['bb_width_median']):
                trend_regimes.append("Unknown")
                volatility_regimes.append("Unknown")
                combined_regimes.append("Unknown")
                continue

            # 1. Trend Classification
            # ADX > threshold implies active trend; EMA slope confirms direction
            if row['adx'] >= self.trend_threshold:
                if row['ema_slope'] > 0.01:  # Positive threshold to filter flat movements
                    trend_state = "Trending Bullish"
                elif row['ema_slope'] < -0.01:
                    trend_state = "Trending Bearish"
                else:
                    trend_state = "Trending"
            elif row['adx'] <= self.range_threshold:
                trend_state = "Ranging"
            else:
                # Transference state or normal breathing phase
                trend_state = "Moderate Trend"

            # 2. Volatility Classification
            # Uses current BB width or ATR vs historical running average/median
            is_bb_high = row['bb_width'] > (row['bb_width_median'] * 1.25)
            is_atr_high = row['atr_pct'] > (row['atr_pct_median'] * 1.25)
            
            is_bb_low = row['bb_width'] < (row['bb_width_median'] * 0.75)
            is_atr_low = row['atr_pct'] < (row['atr_pct_median'] * 0.75)

            if is_bb_high or is_atr_high:
                vol_state = "High Volatility"
            elif is_bb_low or is_atr_low:
                vol_state = "Low Volatility"
            else:
                vol_state = "Normal Volatility"

            # 3. Combined primary designation
            # Yields a single label prioritizing extremes or primary behavior
            if vol_state == "High Volatility":
                combined_state = "High Volatility"
            elif trend_state in ["Trending Bullish", "Trending Bearish", "Trending"]:
                combined_state = "Trending"
            elif trend_state == "Ranging":
                combined_state = "Ranging"
            elif vol_state == "Low Volatility":
                combined_state = "Low Volatility"
            else:
                combined_state = "Normal/Quiet"

            trend_regimes.append(trend_state)
            volatility_regimes.append(vol_state)
            combined_regimes.append(combined_state)

        data['regime_trend'] = trend_regimes
        data['regime_volatility'] = volatility_regimes
        data['market_regime'] = combined_regimes  # Dominant class

        return data
