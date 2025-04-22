
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import random
import time
import string
import io
import base64

# Set page configuration
st.set_page_config(
    page_title="Name-Based Portfolio Analyzer",
    page_icon="📈",
    layout="wide"
)

# Custom CSS for styling
st.markdown('''<style>    .main-header {        font-size: 2.5rem;        color: #0F2E5A;  /* Darker blue for better contrast */        text-align: center;        margin-bottom: 1rem;    }    .sub-header {        font-size: 1.5rem;        color: #1A4B8C;  /* Darker blue for better contrast */        margin-top: 2rem;        margin-bottom: 1rem;    }    .info-text {        font-size: 1rem;        color: #333333;  /* Darker text for better contrast */    }    .highlight {        background-color: #E1EFFE;  /* Lighter blue background */        padding: 1rem;        border-radius: 0.5rem;        border-left: 4px solid #2563EB;    }    .metric-card {        background-color: #F0F4F8;  /* Slightly darker background for better contrast */        padding: 1rem;        border-radius: 0.5rem;        margin: 0.5rem 0;        box-shadow: 0 1px 3px rgba(0,0,0,0.1);  /* Add subtle shadow */    }    .footer {        text-align: center;        margin-top: 3rem;        color: #4A5568;  /* Darker text for better contrast */        font-size: 0.8rem;    }</style>''', unsafe_allow_html=True)
# Header
st.markdown('<h1 class="main-header">Name-Based Portfolio Analyzer</h1>', unsafe_allow_html=True)
st.markdown('<p class="info-text">This app creates a portfolio of stocks based on the letters in your name and analyzes its performance.</p>', unsafe_allow_html=True)

# Sidebar for inputs
with st.sidebar:
    st.header("Settings")
    name = st.text_input("Enter your full name:", "John Average Doe")
    
    years = st.slider("Analysis period (years):", min_value=1, max_value=10, value=5)
    
    risk_free_rate = st.number_input(
        "Annual Risk-Free Rate (%):", 
        min_value=0.0, 
        max_value=10.0, 
        value=2.0,
        step=0.1
    ) / 100
    
    max_search_time = st.slider(
        "Maximum ticker search time (seconds):", 
        min_value=5, 
        max_value=60, 
        value=20
    )
    
    max_tickers = st.slider(
        "Maximum number of tickers:", 
        min_value=5, 
        max_value=30, 
        value=20
    )
    
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
    1. The app extracts letters from your name
    2. It searches for valid stock ticker symbols
    3. It analyzes historical performance
    4. It compares equal-weighted vs letter-count weighted portfolios
    """)

# Function to find valid tickers from a name
@st.cache_data
def find_tickers_from_name(name, max_time=20, max_tickers=20):
    # Remove spaces and convert to uppercase
    name = name.replace(" ", "").upper()
    
    # Initialize variables
    valid_tickers = []
    used_tickers = set()  # Track tickers that have been used
    remaining_letters = list(name)
    start_time = time.time()
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while (len(remaining_letters) > 0 and 
           len(valid_tickers) < max_tickers and 
           time.time() - start_time < max_time):
        
        # Update progress
        progress = min(1.0, (time.time() - start_time) / max_time)
        progress_bar.progress(progress)
        status_text.text(f"Searching for tickers... Found {len(valid_tickers)} so far")
        
        # Determine how many letters to select (up to 4 or remaining letters)
        max_letters = min(4, len(remaining_letters))
        if max_letters == 0:
            break
            
        num_letters = random.randint(1, max_letters)
        
        # Randomly select letters from the remaining set
        selected_indices = random.sample(range(len(remaining_letters)), num_letters)
        selected_indices.sort(reverse=True)  # Sort in reverse to remove properly
        
        # Create the potential ticker
        ticker = ""
        for idx in selected_indices:
            ticker += remaining_letters[idx]
        
        # Check if it's a valid ticker
        try:
            info = yf.Ticker(ticker).info
            # Check if we got valid data back (market cap is a good indicator)
            if 'marketCap' in info and info['marketCap'] is not None:
                if ticker not in used_tickers:  # Only add if not already used
                    valid_tickers.append(ticker)
                    used_tickers.add(ticker)  # Mark as used
                
                # Remove the used letters
                for idx in selected_indices:
                    remaining_letters.pop(idx)
            else:
                # Not a valid ticker, continue
                pass
        except Exception as e:
            # Not a valid ticker or error occurred, continue
            pass
    
    progress_bar.progress(1.0)
    status_text.text(f"Search completed. Found {len(valid_tickers)} valid tickers.")
    
    return valid_tickers, ''.join(remaining_letters)

# Function to get historical data and calculate returns
@st.cache_data
def get_historical_data(tickers, years=5):
    # Set the time period
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years*365)
    
    # Format dates for yfinance
    start_date_str = start_date.strftime('%Y-%m-%d')
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    # Fetch monthly data for all tickers
    monthly_data = {}
    valid_tickers = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(tickers):
        progress = (i + 1) / len(tickers)
        progress_bar.progress(progress)
        status_text.text(f"Fetching data for {ticker}... ({i+1}/{len(tickers)})")
        
        try:
            # Get monthly data
            data = yf.download(ticker, start=start_date_str, end=end_date_str, interval='1mo', progress=False)
            
            if len(data) > 0:
                # Check the structure of the data
                if isinstance(data.columns, pd.MultiIndex):
                    # If MultiIndex, get the 'Close' column
                    data_close = data[('Close', ticker)]
                    returns = data_close.pct_change()
                else:
                    # If regular columns
                    data_close = data['Close']
                    returns = data_close.pct_change()
                    
                monthly_data[ticker] = returns
                valid_tickers.append(ticker)
        except Exception as e:
            # Skip this ticker if there's an error
            pass
    
    progress_bar.progress(1.0)
    status_text.text(f"Data fetching completed. {len(valid_tickers)} valid tickers with data.")
    
    # Create a DataFrame with all monthly returns
    if valid_tickers:
        returns_df = pd.DataFrame({ticker: monthly_data[ticker] for ticker in valid_tickers})
        
        # Drop the first row (NaN due to pct_change)
        returns_df = returns_df.dropna()
        
        return returns_df, valid_tickers, start_date_str, end_date_str
    else:
        return None, [], start_date_str, end_date_str


# Function to calculate portfolio statistics
def calculate_portfolio_stats(returns_df, valid_tickers, risk_free_rate):
    if len(valid_tickers) == 0:
        return None, None, None, None, None, None
    
    # Make sure we only use tickers that are in the returns_df
    available_tickers = [ticker for ticker in valid_tickers if ticker in returns_df.columns]
    
    if len(available_tickers) == 0:
        return None, None, None, None, None, None
    
    # Filter returns_df to only include available tickers
    filtered_returns_df = returns_df[available_tickers]
    
    # 1. Equal-weighted portfolio
    equal_weights = np.ones(len(available_tickers)) / len(available_tickers)
    equal_weighted_returns = filtered_returns_df.dot(equal_weights)
    
    # 2. Letter-count weighted portfolio
    letter_counts = np.array([len(ticker) for ticker in available_tickers])
    letter_weights = letter_counts / letter_counts.sum()
    letter_weighted_returns = filtered_returns_df.dot(letter_weights)
    
    # Calculate portfolio statistics
    monthly_risk_free = risk_free_rate / 12  # Convert annual to monthly
    
    # Function to calculate portfolio statistics
    def calculate_stats(returns, name):
        avg_return = returns.mean() * 12  # Annualized
        std_dev = returns.std() * np.sqrt(12)  # Annualized
        sharpe_ratio = (avg_return - risk_free_rate) / std_dev
        
        return {
            'Portfolio': name,
            'Annualized Return': avg_return,
            'Annualized Volatility': std_dev,
            'Sharpe Ratio': sharpe_ratio
        }
    
    # Calculate statistics for both portfolios
    equal_stats = calculate_stats(equal_weighted_returns, 'Equal-Weighted')
    letter_stats = calculate_stats(letter_weighted_returns, 'Letter-Count Weighted')
    
    # Calculate cumulative returns
    cumulative_returns = (1 + filtered_returns_df).cumprod()
    equal_cumulative = (1 + equal_weighted_returns).cumprod()
    letter_cumulative = (1 + letter_weighted_returns).cumprod()
    
    # Create weights dataframe
    weights_df = pd.DataFrame({
        'Ticker': available_tickers,
        'Equal Weight': equal_weights,
        'Letter Count': letter_counts,
        'Letter Weight': letter_weights
    })
    
    return (equal_stats, letter_stats, cumulative_returns, 
            equal_cumulative, letter_cumulative, weights_df)

def create_plots(cumulative_returns, equal_cumulative, letter_cumulative, valid_tickers):
    # 1. Cumulative returns plot
    fig1, ax1 = plt.subplots(figsize=(9, 6))
    
    # Set the background color and grid
    ax1.set_facecolor('#FFFFFF')
    ax1.grid(True, linestyle='-', color='#D1D5DB', alpha=0.7)
    
    # Plot individual stock cumulative returns as dotted lines
    for ticker in valid_tickers:
        ax1.plot(cumulative_returns.index, cumulative_returns[ticker], 
                 linestyle=':', linewidth=1, alpha=0.5, label=ticker)
    
    # Plot portfolio cumulative returns as solid lines
    ax1.plot(equal_cumulative.index, equal_cumulative, 
             color='#3730A3', linewidth=2.5, label='Equal-Weighted Portfolio')
    ax1.plot(letter_cumulative.index, letter_cumulative, 
             color='#B91C1C', linewidth=2.5, label='Letter-Count Weighted Portfolio')
    
    # Format the plot
    ax1.set_title('Cumulative Returns of Stocks and Portfolios', 
              fontsize=20, fontweight='medium', color='#222222', pad=15)
    ax1.set_xlabel('Date', fontsize=16, color='#333333', labelpad=10)
    ax1.set_ylabel('Cumulative Return', fontsize=16, color='#333333', labelpad=10)
    
    # Format the x-axis to show dates nicely
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.tick_params(axis='both', labelsize=14, colors='#555555')
    
    # Add spines with specific color
    for spine in ax1.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(0.8)
    
    # Set axis below the data
    ax1.set_axisbelow(True)
    
    # Add legend below the plot
    ax1.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), 
               ncol=min(4, len(valid_tickers) + 2), fontsize=12, frameon=False)
    
    plt.tight_layout()
    
    # 2. Final values bar chart
    final_values = pd.DataFrame({
        'Individual Stocks': [cumulative_returns[ticker].iloc[-1] for ticker in valid_tickers],
        'Ticker': valid_tickers
    })
    
    # Sort by final value
    final_values = final_values.sort_values('Individual Stocks', ascending=False)
    
    fig2, ax2 = plt.subplots(figsize=(9, 6))
    ax2.set_facecolor('#FFFFFF')
    ax2.grid(True, linestyle='-', color='#D1D5DB', alpha=0.7, axis='y')
    
    # Plot bars for individual stocks
    bars = ax2.bar(final_values['Ticker'], final_values['Individual Stocks'], 
            color='#047857', alpha=0.8)
    
    # Add portfolio final values
    ax2.axhline(y=equal_cumulative.iloc[-1], color='#3730A3', linestyle='-', linewidth=2, 
               label=f'Equal-Weighted Portfolio: {equal_cumulative.iloc[-1]:.2f}')
    ax2.axhline(y=letter_cumulative.iloc[-1], color='#B91C1C', linestyle='-', linewidth=2, 
               label=f'Letter-Weighted Portfolio: {letter_cumulative.iloc[-1]:.2f}')
    
    # Format the plot
    ax2.set_title('Final Portfolio Values', 
              fontsize=20, fontweight='medium', color='#222222', pad=15)
    ax2.set_xlabel('Ticker', fontsize=16, color='#333333', labelpad=10)
    ax2.set_ylabel('Final Value ($1 Initial Investment)', fontsize=16, color='#333333', labelpad=10)
    ax2.tick_params(axis='both', labelsize=14, colors='#555555')
    
    # Add spines with specific color
    for spine in ax2.spines.values():
        spine.set_edgecolor('#333333')
        spine.set_linewidth(0.8)
    
    # Set axis below the data
    ax2.set_axisbelow(True)
    
    # Add legend below the plot
    ax2.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), 
               ncol=2, fontsize=12, frameon=False)
    
    plt.tight_layout()
    
    return fig1, fig2, final_values

# Main app logic
if st.button("Analyze Portfolio"):
    with st.spinner("Finding ticker symbols from your name..."):
        valid_tickers, remaining_letters = find_tickers_from_name(
            name, 
            max_time=max_search_time,
            max_tickers=max_tickers
        )
    
    if not valid_tickers:
        st.error("No valid ticker symbols found in your name. Try a different name or increase the search time.")
    else:
        st.markdown(f'<p style="color: black;" class="highlight">Found {len(valid_tickers)} valid ticker symbols: {", ".join(valid_tickers)}</p>', unsafe_allow_html=True)
        
        if remaining_letters:
            st.info(f"Unused letters from your name: {remaining_letters}")
        
        with st.spinner("Fetching historical data and calculating returns..."):
            returns_df, valid_tickers_with_data, start_date, end_date = get_historical_data(valid_tickers, years)
        
        if not valid_tickers_with_data:
            st.error("Could not fetch historical data for any of the ticker symbols. Try a different name.")
        else:
            st.markdown(f'<p class="highlight" style="color: black;">Successfully fetched data for {len(valid_tickers_with_data)} tickers: {", ".join(valid_tickers_with_data)}</p>', unsafe_allow_html=True)
            
            # Calculate portfolio statistics
            (equal_stats, letter_stats, cumulative_returns, 
             equal_cumulative, letter_cumulative, weights_df) = calculate_portfolio_stats(
                returns_df, valid_tickers_with_data, risk_free_rate
            )
            
            # Display portfolio statistics
            st.markdown('<h2 class="sub-header">Portfolio Statistics</h2>', unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.subheader("Equal-Weighted Portfolio")
                st.metric("Annual Return", f"{equal_stats['Annualized Return']:.2%}")
                st.metric("Annual Volatility", f"{equal_stats['Annualized Volatility']:.2%}")
                st.metric("Sharpe Ratio", f"{equal_stats['Sharpe Ratio']:.4f}")
                st.metric("Final Value ($1 Investment)", f"${equal_cumulative.iloc[-1]:.2f}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.subheader("Letter-Count Weighted Portfolio")
                st.metric("Annual Return", f"{letter_stats['Annualized Return']:.2%}")
                st.metric("Annual Volatility", f"{letter_stats['Annualized Volatility']:.2%}")
                st.metric("Sharpe Ratio", f"{letter_stats['Sharpe Ratio']:.4f}")
                st.metric("Final Value ($1 Investment)", f"${letter_cumulative.iloc[-1]:.2f}")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Display portfolio weights
            st.markdown('<h2 class="sub-header">Portfolio Weights</h2>', unsafe_allow_html=True)
            st.dataframe(weights_df.style.format({
                'Equal Weight': '{:.2%}',
                'Letter Weight': '{:.2%}'
            }))
            
            # Create and display plots
            fig1, fig2, final_values = create_plots(
                cumulative_returns, equal_cumulative, letter_cumulative, valid_tickers_with_data
            )
            
            st.markdown('<h2 class="sub-header">Portfolio Performance</h2>', unsafe_allow_html=True)
            st.pyplot(fig1)
            
            st.markdown('<h2 class="sub-header">Final Portfolio Values</h2>', unsafe_allow_html=True)
            st.pyplot(fig2)
            
            # Display best and worst performing stocks
            best_stock = final_values.iloc[0]
            worst_stock = final_values.iloc[-1]
            
            st.markdown('<h2 class="sub-header">Performance Highlights</h2>', unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.subheader("Best Performing Stock")
                st.metric("Ticker", best_stock['Ticker'])
                st.metric("Return", f"{best_stock['Individual Stocks']:.2f}x")
                st.markdown('</div>', unsafe_allow_html=True)
            
            with col2:
                st.markdown('<div class="metric-card">', unsafe_allow_html=True)
                st.subheader("Worst Performing Stock")
                st.metric("Ticker", worst_stock['Ticker'])
                st.metric("Return", f"{worst_stock['Individual Stocks']:.2f}x")
                st.markdown('</div>', unsafe_allow_html=True)
            
            # Download links for data
            st.markdown('<h2 class="sub-header">Download Data</h2>', unsafe_allow_html=True)
            
            # Function to create a download link
            def get_download_link(df, filename, text):
                csv = df.to_csv(index=True)
                b64 = base64.b64encode(csv.encode()).decode()
                href = f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv">{text}</a>'
                return href
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.markdown(get_download_link(returns_df, "monthly_returns", "Download Monthly Returns"), unsafe_allow_html=True)
            
            with col2:
                st.markdown(get_download_link(cumulative_returns, "cumulative_returns", "Download Cumulative Returns"), unsafe_allow_html=True)
            
            with col3:
                st.markdown(get_download_link(weights_df, "portfolio_weights", "Download Portfolio Weights"), unsafe_allow_html=True)

# Footer
st.markdown('<div class="footer">Created with Streamlit • Data from Yahoo Finance</div>', unsafe_allow_html=True)

# Add a horizontal line
st.markdown("---")

# Add footer
st.markdown('<div style="text-align: center; color: gray; font-size: 0.8em;">Created by Adam Shettle, Filipe Reis, John McClure Jr, Anthony Hall, Connor Barr and Abdul Rehman for MGMT 675, JGSB, Rice University, 2025</div>', unsafe_allow_html=True)

