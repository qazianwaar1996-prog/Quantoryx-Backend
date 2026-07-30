# utils/generate_mock_data.py

import os
import numpy as np
import pandas as pd


def generate_synthetic_ohlcv(
    symbol: str = "EURUSD",
    timeframe: str = "1H",
    bars: int = 9000,
    start_price: float = 1.1000,
    volatility: float = 0.0015,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generates realistic synthetic OHLCV data with cycling regime shifts
    (low volatility → bullish trend → high volatility → bearish trend).

    The regime cycle scales with ``bars`` so long histories retain a
    balanced mix of regimes — important because the walk-forward windows
    span many months of data.

    Parameters
    ----------
    bars:
        Number of price bars. The default (9000) gives roughly a year of
        1H data, enough for the default 180/60-day walk-forward windows.
    seed:
        RNG seed for reproducible datasets.
    """
    rng = np.random.default_rng(seed)  # Reproducible, modern NumPy generator

    # Generate timestamp index
    freq_map = {"1H": "h", "H1": "h", "4H": "4h", "H4": "4h", "1D": "D", "D1": "D"}
    freq = freq_map.get(timeframe, "h")
    timestamps = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=bars, freq=freq)

    close_prices = []
    current_price = start_price

    # Repeating regime cycle: each phase spans a quarter of a ~1000-bar cycle,
    # so the mix stays balanced regardless of total length.
    cycle = 1000
    for i in range(bars):
        phase = (i % cycle) / cycle  # 0.0 → 1.0 within each cycle
        if phase < 0.25:
            change = rng.normal(0, volatility * 0.5)            # Low volatility range
        elif phase < 0.50:
            change = rng.normal(volatility * 0.3, volatility * 0.8)   # Bullish trend
        elif phase < 0.75:
            change = rng.normal(0, volatility * 2.5)            # High volatility
        else:
            change = rng.normal(-volatility * 0.3, volatility * 0.8)  # Bearish trend

        current_price += change
        # Force a reasonable floor to avoid negative currency values
        current_price = max(0.5000, current_price)
        close_prices.append(current_price)
        
    df = pd.DataFrame(index=timestamps)
    df['close'] = close_prices
    
    # Synthesize corresponding High, Low, Open, Volume metrics
    noise_range = df['close'] * 0.0015
    df['open'] = df['close'].shift(1).fillna(start_price) + rng.normal(0, noise_range * 0.1)

    # Ensure High is strictly the maximum and Low is the minimum
    df['high'] = df[['open', 'close']].max(axis=1) + np.abs(rng.normal(noise_range, noise_range * 0.2))
    df['low'] = df[['open', 'close']].min(axis=1) - np.abs(rng.normal(noise_range, noise_range * 0.2))
    df['volume'] = rng.integers(100, 5000, size=bars)
    
    # Correct any edge-case crossovers
    df['high'] = df[['high', 'open', 'close']].max(axis=1)
    df['low'] = df[['low', 'open', 'close']].min(axis=1)
    
    return df


def main():
    output_dir = "data"
    os.makedirs(output_dir, exist_ok=True)
    
    symbol = "EURUSD"
    timeframe = "1H"
    filename = f"{symbol}_{timeframe}.csv"
    filepath = os.path.join(output_dir, filename)
    
    print(f"[+] Generating realistic mock data for {symbol} ({timeframe})...")
    df = generate_synthetic_ohlcv(symbol=symbol, timeframe=timeframe, bars=1200)
    
    # Save to directory
    df.to_csv(filepath)
    print(f"[+] Dataset created and saved to: {filepath}")
    print(f"    - Period: {df.index[0]} to {df.index[-1]}")
    print(f"    - Total bars: {len(df)}")


if __name__ == "__main__":
    main()
