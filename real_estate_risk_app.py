# Real Estate Risk App - Optimized Version with Enhanced ATTOM API
import streamlit as st
import plotly.express as px
import pandas as pd
import numpy as np
import requests
from numpy_financial import irr
import folium
from streamlit_folium import folium_static
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from datetime import datetime

# Initialize variables to prevent NameError
use_fred = False
use_rentcast = False
use_attom = False
use_map = False
fred_data = {}
attom_data = {}
has_neighborhood_data = False
location_text = ""
coordinates_text = ""
walkability_score = 0
transit_score = 0
bike_score = 0
amenities_df = pd.DataFrame()
custom_notes = ""

# Helper function to get rating text based on score
def get_rating_text(score):
    if score >= 90:
        return "Excellent"
    elif score >= 70:
        return "Very Good"
    elif score >= 50:
        return "Average"
    elif score >= 30:
        return "Below Average"
    else:
        return "Poor"

# Add caching decorators for API calls
@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_fred_data(api_key, series_ids):
    """Fetch multiple FRED data series in a single function to improve caching"""
    fred_data = {}
    for series_id, series_name in series_ids.items():
        url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&limit=1&sort_order=desc"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if "observations" in data and data["observations"]:
                latest_obs = data["observations"][0]
                fred_data[series_id] = {
                    "name": series_name, 
                    "value": latest_obs["value"], 
                    "date": latest_obs["date"]
                }
    return fred_data

# Enhanced ATTOM API function
@st.cache_data(ttl=7200, show_spinner=False)  # Cache for 2 hours
def get_attom_data(api_key, zip_code, commercial_type):
    """Fetch ATTOM data with caching - modified for better data retrieval"""
    attom_data = {}
    
    # First try a broader search - just by ZIP code without filtering by property type
    attom_url = f"https://api.gateway.attomdata.com/propertyapi/v1.0.0/property/basicprofile"
    attom_headers = {
        "apikey": api_key,
        "Accept": "application/json"
    }
    
    # Use more generalized parameters first - just search by ZIP
    attom_params = {
        "postalcode": zip_code,
        "pagesize": 25  # Get more properties to increase chances of finding commercial ones
    }
    
    try:
        st.sidebar.info(f"Searching for properties in ZIP {zip_code}...")
        response = requests.get(attom_url, headers=attom_headers, params=attom_params)
        
        if response.status_code == 200:
            data = response.json()
            
            if "property" in data and len(data["property"]) > 0:
                # Filter for commercial properties after retrieval
                commercial_properties = []
                
                for prop in data["property"]:
                    # Check if this is a commercial property based on property use type
                    is_commercial = False
                    
                    # Look for property use indicators in various fields
                    if "proptype" in prop and prop["proptype"]:
                        if "commercial" in str(prop["proptype"]).lower():
                            is_commercial = True
                    
                    if "propertyType" in prop and prop["propertyType"]:
                        if "commercial" in str(prop["propertyType"]).lower():
                            is_commercial = True
                    
                    # Look for use code - typically 400-500 range is commercial
                    if "propuse" in prop and prop["propuse"] and str(prop["propuse"]).isdigit():
                        use_code = int(prop["propuse"])
                        if 400 <= use_code < 500:
                            is_commercial = True
                    
                    # Check if we're looking for multifamily (sometimes coded differently)
                    if commercial_type == "multifamily":
                        if "propsubtype" in prop and prop["propsubtype"]:
                            if "apartment" in str(prop["propsubtype"]).lower() or "multi" in str(prop["propsubtype"]).lower():
                                is_commercial = True
                    
                    # If this matches our commercial criteria, add it to our list
                    if is_commercial:
                        commercial_properties.append(prop)
                
                # If we found commercial properties, process them
                if commercial_properties:
                    attom_data["property_type"] = commercial_type
                    attom_data["property_count"] = len(commercial_properties)
                    
                    # Process property values
                    total_value = 0
                    total_sqft = 0
                    valid_property_count = 0
                    
                    for prop in commercial_properties:
                        # Look for property value
                        if "assessment" in prop:
                            if "assessed" in prop["assessment"] and "assdttlvalue" in prop["assessment"]["assessed"]:
                                try:
                                    value = float(prop["assessment"]["assessed"]["assdttlvalue"])
                                    if value > 0:
                                        total_value += value
                                        valid_property_count += 1
                                except (ValueError, TypeError):
                                    pass
                            elif "market" in prop["assessment"] and "mktttlvalue" in prop["assessment"]["market"]:
                                try:
                                    value = float(prop["assessment"]["market"]["mktttlvalue"])
                                    if value > 0:
                                        total_value += value
                                        valid_property_count += 1
                                except (ValueError, TypeError):
                                    pass
                        
                        # Look for square footage
                        if "building" in prop and "size" in prop["building"]:
                            if "universalsize" in prop["building"]["size"]:
                                try:
                                    sqft = float(prop["building"]["size"]["universalsize"])
                                    if sqft > 0:
                                        total_sqft += sqft
                                except (ValueError, TypeError):
                                    pass
                            elif "grosssize" in prop["building"]["size"]:
                                try:
                                    sqft = float(prop["building"]["size"]["grosssize"])
                                    if sqft > 0:
                                        total_sqft += sqft
                                except (ValueError, TypeError):
                                    pass
                    
                    # Calculate averages
                    if valid_property_count > 0:
                        attom_data["avg_value"] = total_value / valid_property_count
                        
                        if total_sqft > 0:
                            avg_sqft = total_sqft / valid_property_count
                            attom_data["avg_sqft"] = avg_sqft
                            attom_data["price_per_sqft"] = attom_data["avg_value"] / avg_sqft
                    
                    # Set market cap rates based on property type
                    cap_rates = {
                        "multifamily": 0.055,
                        "office": 0.065,
                        "retail": 0.06,
                        "industrial": 0.052
                    }
                    attom_data["market_cap_rate"] = cap_rates.get(commercial_type, 0.06)
                    
                    st.sidebar.success(f"Found {attom_data['property_count']} commercial properties in ZIP {zip_code}")
                    return attom_data
    
    except Exception as e:
        st.sidebar.warning(f"Error with API call: {str(e)}")
    
    # If the first attempt failed, try with the assessment endpoint
    try:
        st.sidebar.info("Trying alternative data source...")
        attom_url = f"https://api.gateway.attomdata.com/propertyapi/v1.0.0/assessment/detail"
        attom_params = {
            "postalcode": zip_code,
            "propertytype": "commercial",
            "pagesize": 25
        }
        
        response = requests.get(attom_url, headers=attom_headers, params=attom_params)
        
        if response.status_code == 200:
            data = response.json()
            if "property" in data and len(data["property"]) > 0:
                attom_data["property_type"] = commercial_type
                attom_data["property_count"] = len(data["property"])
                
                # Try multiple paths to find property values
                total_value = 0
                total_sqft = 0
                valid_property_count = 0
                
                for prop in data["property"]:
                    property_value = None
                    
                    # Check for assessment data
                    if "assessment" in prop:
                        if "assessed" in prop["assessment"]:
                            assessed = prop["assessment"]["assessed"]
                            
                            # Try multiple possible field names for property value
                            for field in ["assdttlvalue", "totalvalue", "marketvalue", "assessedvalue"]:
                                if field in assessed and assessed[field] is not None:
                                    try:
                                        value = float(assessed[field])
                                        if value > 0:
                                            property_value = value
                                            break
                                    except (ValueError, TypeError):
                                        pass
                        
                        # If not in assessed, check calculations
                        if property_value is None and "calculations" in prop["assessment"]:
                            calc = prop["assessment"]["calculations"]
                            for field in ["calcttlvalue", "calculatedvalue", "totalvalue"]:
                                if field in calc and calc[field] is not None:
                                    try:
                                        value = float(calc[field])
                                        if value > 0:
                                            property_value = value
                                            break
                                    except (ValueError, TypeError):
                                        pass
                    
                    # If no assessment data, try other locations
                    if property_value is None:
                        # Try looking in sale or price data if exists
                        if "sale" in prop:
                            sale = prop["sale"]
                            for field in ["amount", "saleamt", "saleamount", "price"]:
                                if field in sale and sale[field] is not None:
                                    try:
                                        value = float(sale[field])
                                        if value > 0:
                                            property_value = value
                                            break
                                    except (ValueError, TypeError):
                                        pass
                    
                    # If we found a valid property value, count it
                    if property_value is not None:
                        total_value += property_value
                        valid_property_count += 1
                    
                    # Get square footage if available
                    if "building" in prop and "size" in prop["building"] and "grosssize" in prop["building"]["size"]:
                        try:
                            sqft = float(prop["building"]["size"]["grosssize"] or 0)
                            if sqft > 0:
                                total_sqft += sqft
                        except (ValueError, TypeError):
                            pass
                
                # Calculate averages
                if valid_property_count > 0:
                    avg_value = total_value / valid_property_count
                    avg_sqft = total_sqft / attom_data["property_count"] if attom_data["property_count"] > 0 and total_sqft > 0 else 0
                    
                    # Store commercial metrics
                    attom_data["avg_value"] = avg_value
                    attom_data["avg_sqft"] = avg_sqft
                    
                    # Calculate price per sq ft only if we have valid square footage
                    if avg_sqft > 0:
                        attom_data["price_per_sqft"] = avg_value / avg_sqft
                    
                    # Set market cap rates based on property type
                    cap_rates = {
                        "multifamily": 0.055,
                        "office": 0.065,
                        "retail": 0.06,
                        "industrial": 0.052
                    }
                    attom_data["market_cap_rate"] = cap_rates.get(commercial_type, 0.06)
                    
                    # Log what we've found
                    if valid_property_count > 0:
                        st.sidebar.success(f"Found {valid_property_count} properties with value data")
                        return attom_data
    except Exception:
        pass
    
    # If we still don't have values, use default values based on property type
    st.sidebar.info("Using default values based on property type")
    attom_data["property_type"] = commercial_type
    attom_data["property_count"] = 0  # Important: Set to 0 to indicate no properties found
    
    if commercial_type == "multifamily":
        attom_data["avg_value"] = 1500000  # Default for multifamily
    elif commercial_type == "office":
        attom_data["avg_value"] = 2000000  # Default for office
    elif commercial_type == "retail":
        attom_data["avg_value"] = 1800000  # Default for retail
    elif commercial_type == "industrial":
        attom_data["avg_value"] = 1200000  # Default for industrial
    else:
        attom_data["avg_value"] = 1500000  # General default
    
    # Add market cap rates even for defaults
    cap_rates = {
        "multifamily": 0.055,
        "office": 0.065,
        "retail": 0.06,
        "industrial": 0.052
    }
    attom_data["market_cap_rate"] = cap_rates.get(commercial_type, 0.06)
    
    st.sidebar.warning(f"No commercial properties found in ZIP {zip_code}")
    return attom_data

@st.cache_data(ttl=3600)  # Cache for 1 hour
def get_rentcast_data(api_key, zip_code):
    """Fetch RentCast data with caching"""
    url = f"https://api.rentcast.io/v1/properties/market-rents?postalCode={zip_code}"
    headers = {"X-API-Key": api_key}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        rents = [r.get("rent") for r in data.get("rentalListings", []) if r.get("rent")]
        base_rent = int(np.mean(rents)) if rents else 2500
        return base_rent
    return 2500  # Default if API fails

@st.cache_data(ttl=6000)  # Cache for 1 hour 40 minutes
def get_location_data(zip_code):
    """Fetch location data with caching"""
    osm_url = f"https://nominatim.openstreetmap.org/search?format=json&limit=1&postalcode={zip_code}&country=USA"
    response = requests.get(osm_url, headers={"User-Agent": "RealEstateApp/1.0"})
    if response.status_code == 200:
        return response.json()
    return []

@st.cache_data(ttl=7200)  # Cache for 2 hours
def fetch_amenities_batch(lat, lon, amenity_queries):
    """Batch fetch amenities data using a single Overpass API query"""
    # Build a single query for all amenities to reduce API calls
    query_parts = []
    for key, value in amenity_queries:
        query_parts.append(f'node["{key}"="{value}"](around:1609,{lat},{lon});')
        query_parts.append(f'way["{key}"="{value}"](around:1609,{lat},{lon});')
        query_parts.append(f'relation["{key}"="{value}"](around:1609,{lat},{lon});')
    
    overpass_query = f"""
    [out:json];
    (
      {" ".join(query_parts)}
    );
    out center;
    """
    
    overpass_url = "https://overpass-api.de/api/interpreter"
    response = requests.get(overpass_url, params={"data": overpass_query})
    
    if response.status_code == 200:
        return response.json()
    return {"elements": []}

# Function to create PDF report
def create_pdf_report():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Add custom styles
    styles.add(ParagraphStyle(name='CenteredTitle', parent=styles['Title'], alignment=TA_CENTER))
    
    # Container for the 'Flowable' objects
    elements = []
    
    # Title
    elements.append(Paragraph(f"Real Estate Investment Analysis Report", styles['CenteredTitle']))
    elements.append(Paragraph(f"ZIP Code: {zip_code} | Analysis Date: {datetime.now().strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Property Summary Section
    elements.append(Paragraph("Property Summary", styles['Heading1']))
    
    # Property details table
    data = [
        ["Purchase Price", f"${price:,.0f}"],
        ["Down Payment", f"${price * down_pct:,.0f} ({down_pct:.0%})"],
        ["Monthly Rent/Income", f"${rent:,.0f}"],
        ["Scenario", scenario]
    ]
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Location Information if available
    if use_map and location_text and coordinates_text:
        elements.append(Paragraph("Location Information", styles['Heading1']))
        
        # Extract location information
        elements.append(Paragraph(location_text, styles['Normal']))
        elements.append(Paragraph(coordinates_text, styles['Normal']))
            
        # Add neighborhood metrics if available
        if has_neighborhood_data:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph("Neighborhood Metrics", styles['Heading2']))
            
            # Create table for walkability scores
            walk_data = [
                ["Metric", "Score", "Rating"],
                ["Walk Score", f"{walkability_score}", get_rating_text(walkability_score)],
                ["Transit Score", f"{transit_score}", get_rating_text(transit_score)],
                ["Bike Score", f"{bike_score}", get_rating_text(bike_score)]
            ]
            
            walk_table = Table(walk_data)
            walk_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ]))
            
            elements.append(walk_table)
            elements.append(Spacer(1, 12))
            
            # Add amenity counts
            elements.append(Paragraph("Nearby Amenities (1 mile radius)", styles['Heading3']))
            
            # Create table for amenity counts
            amenity_data = [["Category", "Count"]]
            
            # Add rows for each amenity category
            for index, row in amenities_df.iterrows():
                amenity_data.append([row["Category"].capitalize(), str(row["Count"])])
            
            amenity_table = Table(amenity_data)
            amenity_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ]))
            
            elements.append(amenity_table)
        
        # Add a note about OpenStreetMap
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Map data © OpenStreetMap contributors", styles['Italic']))
        elements.append(Spacer(1, 12))
    
    # Financial Analysis Section
    elements.append(Paragraph("Financial Analysis", styles['Heading1']))
    
    # Key metrics table - different metrics based on property type
    if property_type.startswith("Commercial"):
        # Commercial report metrics
        commercial_type = property_type.split(" - ")[1] if " - " in property_type else "Commercial"
        
        data = [
            ["Metric", "Value"],
            ["Property Type", commercial_type],
            ["Net Operating Income (NOI)", f"${noi:,.0f}"],
            ["Cap Rate", f"{cap_rate:.2%}"]
        ]
        
        # Add property-specific metrics
        if commercial_type.lower() == "office" or commercial_type.lower() == "retail":
            if "price_per_sqft" in attom_data:
                data.append(["Market Price per Sq Ft", f"${attom_data['price_per_sqft']:.2f}"])
                data.append(["Property Size (Avg)", f"{attom_data.get('avg_sqft', 0):,.0f} sq ft"])
        
        data.extend([
            ["Cash-on-Cash Return", f"{coc_return:.2%}"],
            ["IRR", f"{project_irr:.2%}"],
            ["Total ROI", f"{roi:.2%}"],
            ["Monthly Mortgage", f"${monthly_mortgage:,.0f}"],
            ["Annual Depreciation Benefit", f"${annual_depreciation:,.0f}"],
            ["Tax Savings from Depreciation", f"${depreciation_tax_shield:,.0f}"]
        ])
        
        # If we have ATTOM data, add market statistics
        if "property_count" in attom_data and attom_data["property_count"] > 0:
            elements.append(Paragraph("Market Data from ATTOM", styles['Heading2']))
            attom_market_data = [
                ["Metric", "Value"],
                ["Properties in ZIP Code", f"{attom_data['property_count']}"],
                ["Average Market Value", f"${attom_data['avg_value']:,.0f}"],
                ["Market Cap Rate", f"{attom_data.get('market_cap_rate', 0.06):.2%}"]
            ]
            
            attom_table = Table(attom_market_data)
            attom_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ]))
            
            elements.append(attom_table)
            elements.append(Spacer(1, 12))
            
    else:  # Residential
        data = [
            ["Metric", "Value"],
            ["Net Operating Income (NOI)", f"${noi:,.0f}"],
            ["Price-to-Rent Ratio", f"{price_to_rent_ratio:.2f}"],
            ["Gross Rent Multiplier", f"{grm:.2f}"],
            ["Cash-on-Cash Return", f"{coc_return:.2%}"],
            ["IRR", f"{project_irr:.2%}"],
            ["Total ROI", f"{roi:.2%}"],
            ["Monthly Mortgage", f"${monthly_mortgage:,.0f}"]
        ]
    
    t = Table(data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
    ]))
    
    elements.append(t)
    elements.append(Spacer(1, 12))
    
    # Yearly Cash Flow Table
    elements.append(Paragraph("Yearly Cash Flow Projection", styles['Heading2']))
    
    # Create header row and data rows for cash flow table
    cf_data = [["Year", "Cash Flow", "Property Value", "Cumulative Returns"]]
    
    for i, year in enumerate(range(1, years + 1)):
        cf_data.append([
            f"Year {year}", 
            f"${annual_cash_flows[i]:,.0f}", 
            f"${annual_appreciation[i]:,.0f}", 
            f"${cumulative_returns[i]:,.0f}"
        ])
    
    cf_table = Table(cf_data)
    cf_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (1, 1), (-1, -1), 'RIGHT'),
    ]))
    
    elements.append(cf_table)
    elements.append(Spacer(1, 12))
    
    # Add depreciation analysis for commercial properties
    if property_type.startswith("Commercial"):
        elements.append(Paragraph("Depreciation Tax Benefits", styles['Heading2']))
        elements.append(Paragraph(
            "Commercial real estate investors benefit from depreciation deductions, which are non-cash expenses "
            "that reduce taxable income. The table below shows how depreciation impacts the effective cash flow "
            "of this investment.", styles['Normal']
        ))
        elements.append(Spacer(1, 6))
        
        # Improved display of depreciation impact - Fixed to handle extreme percentages
        if cash_flow <= 0:
            impact_text = f"+${depreciation_tax_shield:,.0f} (transforms to positive cash flow)"
        elif depreciation_tax_shield > cash_flow * 10:
            impact_text = f"+${depreciation_tax_shield:,.0f} (substantially exceeds pre-tax cash flow)"
        else:
            percentage = min(1000, (depreciation_tax_shield/cash_flow)*100)
            impact_text = f"+${depreciation_tax_shield:,.0f} ({percentage:.0f}%)"
        
        # Depreciation details table with improved impact display
        depr_data = [
            ["Metric", "Value"],
            ["Annual Depreciation", f"${annual_depreciation:,.0f}"],
            ["Tax Rate", f"{tax:.0%}"],
            ["Annual Tax Savings", f"${depreciation_tax_shield:,.0f}"],
            ["Cash Flow Before Tax Benefits", f"${cash_flow:,.0f}"],
            ["Effective Cash Flow With Tax Benefits", f"${cash_flow_with_tax_benefits:,.0f}"],
            ["Improvement to Cash Flow", impact_text]
        ]
        
        depr_table = Table(depr_data)
        depr_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ]))
        
        elements.append(depr_table)
        elements.append(Spacer(1, 12))
    
    # Custom Notes Section
    if custom_notes:
        elements.append(Paragraph("Additional Notes", styles['Heading1']))
        elements.append(Paragraph(custom_notes, styles['Normal']))
        elements.append(Spacer(1, 12))
    
    # Disclaimer
    elements.append(Paragraph("Disclaimer", styles['Heading1']))
    elements.append(Paragraph("This report is for informational purposes only and should not be considered as financial advice. All projections are estimates based on available data and assumptions. Actual results may vary. We recommend consulting with a financial advisor before making investment decisions.", styles['Normal']))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Map data © OpenStreetMap contributors", styles['Italic']))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

# Set page configuration
st.set_page_config(page_title="Real Estate Risk App", layout="wide")
st.title("Real Estate Investment Risk App")
st.caption("Created by Chris Menard, Chris Ejike-Ukah, Annaissa Flores, Jaclyn Hernandez, and Quinn Zhang for MGMT 675, JGSB, Rice University, 2025")

# ------------ SIDEBAR INPUTS ------------ #
st.sidebar.header("Property Inputs")

# Basic property inputs
property_type = st.sidebar.selectbox("Property Type", 
                                    ["Residential", 
                                     "Commercial - Multifamily",
                                     "Commercial - Office",
                                     "Commercial - Retail",
                                     "Commercial - Industrial"])
zip_code = st.sidebar.text_input("ZIP Code", value="77002")
price = st.sidebar.number_input("Purchase Price ($)", 50000, 10000000, 350000, step=5000)

# API Integration Options
st.sidebar.subheader("Data Sources")
use_rentcast = st.sidebar.checkbox("Use RentCast API (Residential)", value=True)
use_attom = st.sidebar.checkbox("Use ATTOM API (Commercial)", value=True)
use_fred = st.sidebar.checkbox("Use FRED Economic Data", value=True)
use_map = st.sidebar.checkbox("Enable Property Location Map", value=True)

# Financing inputs
st.sidebar.subheader("Financing")
# Adjusted down payment defaults based on property type
if property_type.startswith("Commercial"):
    commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
    if commercial_type == "multifamily":
        default_down = 0.25  # 25% for multifamily
    elif commercial_type == "office" or commercial_type == "retail":
        default_down = 0.30  # 30% for office and retail
    else:
        default_down = 0.30  # 30% for other commercial
else:
    default_down = 0.20  # 20% for residential
    
down_pct = st.sidebar.slider("Down Payment (%)", 0.0, 1.0, default_down, step=0.01)

# Initialize FRED variables
current_mortgage_rate = 0.06  # Default
current_vacancy_rate = 0.05   # Default
use_fred_mortgage_rate = False
use_fred_vacancy_rate = False

# FRED API integration with caching
if use_fred:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### FRED Economic Indicators")
    
    try:
        # Use the provided FRED API key
        fred_api_key = "38f18ab1d59680615c37138b3c5f5302"
        
        # Define which FRED series to fetch
        fred_series = {
            "MORTGAGE30US": "Mortgage Rate",
            "CSUSHPISA": "Home Price Index",
            "RRVRUSQ156N": "Rental Vacancy Rate"
        }
        
        # Add commercial-specific indicators if applicable
        if property_type.startswith("Commercial"):
            fred_series["COMPRMS"] = "Commercial Property Price Index"
            fred_series["EVACANTUSQ176N"] = "Vacant Housing Units"
        
        with st.sidebar:
            with st.spinner("Fetching economic data..."):
                # Use cached function to fetch all FRED data at once
                fred_data = get_fred_data(fred_api_key, fred_series)
                
                # Display results in sidebar
                for series_id, data in fred_data.items():
                    try:
                        value_float = float(data["value"])
                        if series_id == "MORTGAGE30US":
                            formatted_value = f"{value_float:.2f}%"
                        elif series_id == "CSUSHPISA" or series_id == "COMPRMS":
                            formatted_value = f"{value_float:.1f}"
                        elif series_id == "RRVRUSQ156N":
                            formatted_value = f"{value_float:.1f}%"
                        elif series_id == "EVACANTUSQ176N":
                            formatted_value = f"{value_float:.0f} thousand units"
                        else:
                            formatted_value = f"{value_float}"
                        
                        st.sidebar.success(f"{data['name']}: {formatted_value}")
                    except ValueError:
                        st.sidebar.success(f"{data['name']}: {data['value']}")
        
        # Get FRED mortgage rate if available, or use default
        try:
            current_mortgage_rate = float(fred_data.get("MORTGAGE30US", {}).get("value", 6.0)) / 100
        except (ValueError, TypeError):
            current_mortgage_rate = 0.06  # Default to 6% if FRED data unavailable
            
        # Get FRED vacancy rate if available, or use default
        try:
            if property_type.startswith("Commercial") and "EVACANTUSQ176N" in fred_data:
                # Note: EVACANTUSQ176N is in "Thousands of Units", not a percentage
                # We need to use a default commercial vacancy rate since this is just the count
                # Typical commercial vacancy rates range from 5-15% depending on property type
                commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
                if commercial_type == "multifamily":
                    current_vacancy_rate = 0.055  # 5.5% typical for multifamily
                elif commercial_type == "office":
                    current_vacancy_rate = 0.12   # 12% typical for office
                elif commercial_type == "retail":
                    current_vacancy_rate = 0.08   # 8% typical for retail
                elif commercial_type == "industrial":
                    current_vacancy_rate = 0.05   # 5% typical for industrial
                else:
                    current_vacancy_rate = 0.075  # 7.5% as a general default
            else:
                current_vacancy_rate = float(fred_data.get("RRVRUSQ156N", {}).get("value", 5.0)) / 100
        except (ValueError, TypeError):
            current_vacancy_rate = 0.05 if not property_type.startswith("Commercial") else 0.075
        
        # Allow manual override of FRED data
        use_fred_mortgage_rate = not st.sidebar.checkbox("Override Mortgage Rate")
        use_fred_vacancy_rate = not st.sidebar.checkbox("Override Vacancy Rate")
        
    except Exception as e:
        st.sidebar.warning(f"Failed to load FRED data. Error: {str(e)}")

# Use FRED mortgage rate by default if available
if use_fred_mortgage_rate:
    rate = current_mortgage_rate
    st.sidebar.info(f"Using FRED mortgage rate: {rate*100:.2f}%")
else:
    # Adjusted default rates based on property type
    if property_type.startswith("Commercial"):
        default_rate = current_mortgage_rate * 1.15  # Commercial rates are typically higher
    else:
        default_rate = current_mortgage_rate
        
    rate = st.sidebar.slider("Interest Rate (%)", 1.0, 15.0, float(default_rate*100), step=0.1) / 100

# Adjust loan term based on property type
if property_type.startswith("Commercial"):
    commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
    if commercial_type == "multifamily":
        default_term = 25  # 25 years for multifamily
    else:
        default_term = 20  # 20 years for other commercial
else:
    default_term = 30  # 30 years for residential

years = st.sidebar.slider("Investment Horizon (Years)", 1, 30, 15)
loan_term = st.sidebar.slider("Loan Term (Years)", 5, 30, default_term)

# Operation inputs with FRED defaults when available
st.sidebar.subheader("Operation")

# Adjust expense ratio based on property type
if property_type.startswith("Commercial"):
    commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
    if commercial_type == "multifamily":
        default_expense = 0.40  # 40% for multifamily
    elif commercial_type == "office":
        default_expense = 0.35  # 35% for office
    elif commercial_type == "retail" or commercial_type == "industrial":
        default_expense = 0.20  # 20% for retail/industrial (often NNN leases)
    else:
        default_expense = 0.30
else:
    default_expense = 0.30  # 30% for residential

expenses = st.sidebar.slider("Expense Ratio (% of Income)", 0.0, 1.0, default_expense, step=0.01)

# Use FRED vacancy rate by default if available
if use_fred_vacancy_rate:
    vacancy = current_vacancy_rate
    st.sidebar.info(f"Using vacancy rate: {vacancy*100:.1f}%")
else:
    # Adjust vacancy based on property type
    if property_type.startswith("Commercial"):
        commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
        if commercial_type == "multifamily":
            default_vacancy = 0.05  # 5% for multifamily
        elif commercial_type == "office":
            default_vacancy = 0.10  # 10% for office
        elif commercial_type == "retail":
            default_vacancy = 0.08  # 8% for retail
        elif commercial_type == "industrial":
            default_vacancy = 0.05  # 5% for industrial
        else:
            default_vacancy = 0.07
    else:
        default_vacancy = 0.05  # 5% for residential
        
    vacancy = st.sidebar.slider("Vacancy Rate (%)", 0.0, 0.3, float(default_vacancy*100), step=0.1) / 100

appr = st.sidebar.slider("Appreciation Rate (%)", 0.0, 10.0, 2.5, step=0.1) / 100
tax = st.sidebar.slider("Tax Rate (%)", 0.0, 50.0, 25.0, step=0.1) / 100

# Scenarios
scenario = st.sidebar.selectbox("Economic Scenario", ["Baseline", "Bullish", "Bearish"])

# ATTOM API integration for commercial properties with caching
if use_attom and property_type.startswith("Commercial"):
    st.sidebar.markdown("---")
    st.sidebar.markdown("### ATTOM Commercial Data")
    
    try:
        # ATTOM API call using provided key
        attom_api_key = "408528c60800d53e2f94b51675b3ee8d"
        
        # Prepare ATTOM API request based on property type
        commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
        
        # Use cached function to get ATTOM data
        with st.sidebar:
            with st.spinner("Fetching ATTOM commercial data..."):
                attom_data = get_attom_data(attom_api_key, zip_code, commercial_type)
                
                # Display summary in sidebar
                if "property_count" in attom_data:
                    st.sidebar.success(f"Found {attom_data['property_count']} {commercial_type} properties")
                    if "avg_value" in attom_data:
                        st.sidebar.success(f"Avg Value: ${attom_data['avg_value']:,.0f}")
                    
                    if "avg_sqft" in attom_data and attom_data["avg_sqft"] > 0:
                        st.sidebar.success(f"Avg Size: {attom_data['avg_sqft']:,.0f} sq ft")
                        if "price_per_sqft" in attom_data:
                            st.sidebar.success(f"Price/sq ft: ${attom_data['price_per_sqft']:.2f}")
                    
                    if "market_cap_rate" in attom_data:
                        st.sidebar.success(f"Market Cap Rate: {attom_data['market_cap_rate']:.2%}")
                else:
                    st.sidebar.warning(f"No commercial properties found in ZIP {zip_code}")
                
    except Exception as e:
        st.sidebar.warning(f"Failed to load ATTOM data. Error: {str(e)}")
else:
    if property_type.startswith("Commercial"):
        st.sidebar.warning("ATTOM API is disabled. Enable it to see commercial property data.")

# RentCast section with manual override for residential properties with caching
if property_type == "Residential":
    manual_rent_override = st.sidebar.checkbox("Manual Rent Input")
    if manual_rent_override:
        base_rent = st.sidebar.number_input("Monthly Rent ($)", 500, 10000, 2500, step=50)
        rent_estimate_source = "Manual Input"
    else:
        if use_rentcast:
            try:
                # Use cached function to get RentCast data
                with st.sidebar:
                    with st.spinner("Fetching rental data..."):
                        base_rent = get_rentcast_data("fee971af337e4fca977eb2746bac84c9", zip_code)
                        rent_estimate_source = "RentCast API"
                        st.sidebar.success(f"RentCast: ${base_rent:,.0f}")
            except Exception as e:
                base_rent = 2500
                rent_estimate_source = "Default (API Failed)"
                st.sidebar.warning(f"Failed to load RentCast data. Using default rent: $2,500. Error: {str(e)}")
        else:
            base_rent = 2500
            rent_estimate_source = "Default (APIs Disabled)"
elif property_type.startswith("Commercial"):
    # For commercial properties, we'll use a different approach
    commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
    manual_rent_override = st.sidebar.checkbox("Manual NOI Input")
    
    if manual_rent_override:
        annual_noi = st.sidebar.number_input("Annual NOI ($)", 5000, 1000000, 25000, step=1000)
        base_rent = annual_noi / 12
        rent_estimate_source = "Manual Input"
    else:
        if "market_cap_rate" in attom_data:
            # Get rent based on the property value and market cap rate
            expected_noi = price * attom_data["market_cap_rate"]
            base_rent = expected_noi / 12  # Monthly rent
            rent_estimate_source = "ATTOM Market Cap Rate"
        else:
            # Default commercial rents based on property type  
            if commercial_type == "multifamily":
                cap_rate = 0.055  # 5.5% cap rate
            elif commercial_type == "office":
                cap_rate = 0.065  # 6.5% cap rate
            elif commercial_type == "retail":
                cap_rate = 0.06   # 6% cap rate
            elif commercial_type == "industrial":
                cap_rate = 0.052  # 5.2% cap rate
            else:
                cap_rate = 0.06   # Default 6% cap rate
                
            expected_noi = price * cap_rate
            base_rent = expected_noi / 12  # Monthly rent
            rent_estimate_source = f"Default {commercial_type.capitalize()} Cap Rate ({cap_rate:.1%})"
        
    st.sidebar.success(f"Expected Annual NOI: ${base_rent * 12:,.0f}")
    st.sidebar.success(f"Monthly Income: ${base_rent:,.0f} ({rent_estimate_source})")
else:
    # Fallback for any other property type
    base_rent = 2500
    rent_estimate_source = "Default"

# ------------ MAIN CONTENT AREA ------------ #
# Property summary
st.header("Property Summary")

# Property details and financial summary side by side
col1, col2 = st.columns(2)

with col1:
    st.subheader("Property Details")
    st.write(f"**ZIP Code:** {zip_code}")
    st.write(f"**Purchase Price:** ${price:,.0f}")
    st.write(f"**Down Payment:** ${price * down_pct:,.0f} ({down_pct:.0%})")
    st.write(f"**Loan Amount:** ${price * (1-down_pct):,.0f}")
    
    # Scenario adjusted rent
    rent_multiplier = {"Bullish": 1.2, "Baseline": 1.0, "Bearish": 0.8}[scenario]
    rent = base_rent * rent_multiplier
    st.write(f"**Base Monthly Rent:** ${base_rent:,.0f} ({rent_estimate_source})")
    st.write(f"**Scenario-Adjusted Rent ({scenario}):** ${rent:,.0f}")

# Calculate mortgage payment
loan = price * (1 - down_pct)
r = rate / 12  # Monthly interest rate
n = loan_term * 12  # Number of payments
monthly_mortgage = loan * (r * (1 + r)**n) / ((1 + r)**n - 1) if loan > 0 and r > 0 else 0

# Annual calculations
annual_rent = rent * 12
vacancy_loss = annual_rent * vacancy
effective_income = annual_rent - vacancy_loss
operating_expenses = effective_income * expenses
noi = effective_income - operating_expenses
annual_mortgage = monthly_mortgage * 12

# Cash flow calculation MUST be done before using it in tax benefit calculations
cash_flow = noi - annual_mortgage

# Calculate depreciation for tax benefits (commercial properties only)
if property_type.startswith("Commercial"):
    commercial_type = property_type.split(" - ")[1].lower() if " - " in property_type else ""
    # Set correct depreciation period based on property type
    if commercial_type == "multifamily":
        # Residential (multifamily) uses 27.5 year schedule
        depr_period = 27.5
        building_value_ratio = 0.8  # Assume 80% of property value is building
    else:
        # Commercial buildings use 39 year schedule
        depr_period = 39
        building_value_ratio = 0.8
    
    # Calculate annual depreciation
    annual_depreciation = price * building_value_ratio / depr_period
    
    # Calculate tax shield from depreciation
    depreciation_tax_shield = annual_depreciation * tax
    
    # Now we can safely calculate cash flow with tax benefits
    cash_flow_with_tax_benefits = cash_flow + depreciation_tax_shield
else:
    # Default values for residential properties
    annual_depreciation = price * 0.8 / 27.5  # Residential rate
    depreciation_tax_shield = annual_depreciation * tax
    cash_flow_with_tax_benefits = cash_flow

# Investment metrics
cap_rate = noi / price if price > 0 else 0
coc_return = cash_flow / (price * down_pct) if price * down_pct > 0 else 0
grm = price / annual_rent if annual_rent > 0 else 0  # Gross Rent Multiplier
price_to_rent_ratio = price / (annual_rent) if annual_rent > 0 else 0

with col2:
    st.subheader("Financial Summary")
    st.write(f"**Monthly Mortgage:** ${monthly_mortgage:,.0f}")
    
    # Display different metrics based on property type
    if property_type.startswith("Commercial"):
        # Commercial metrics
        st.write(f"**Annual NOI:** ${noi:,.0f}")
        st.write(f"**Cap Rate:** {cap_rate:.2%}")
        
        # Additional commercial metrics
        if property_type.split(" - ")[1].lower() == "office" or property_type.split(" - ")[1].lower() == "retail":
            # For office and retail, show price per sqft and market comparison
            if "price_per_sqft" in attom_data:
                market_price_per_sqft = attom_data["price_per_sqft"]
                property_price_per_sqft = price / 2500  # Assuming 2500 sqft if not provided
                st.write(f"**Price per Sq Ft:** ${property_price_per_sqft:.2f}")
                st.write(f"**Market Price per Sq Ft:** ${market_price_per_sqft:.2f}")
        
        st.write(f"**Cash Flow (Year 1):** ${cash_flow:,.0f}")
        st.write(f"**Cash-on-Cash Return:** {coc_return:.2%}")
        
    else:  # Residential
        st.write(f"**Annual NOI:** ${noi:,.0f}")
        st.write(f"**Price-to-Rent Ratio:** {price_to_rent_ratio:.2f}")
        st.write(f"**Gross Rent Multiplier:** {grm:.2f}")
        st.write(f"**Cash Flow (Year 1):** ${cash_flow:,.0f}")
        st.write(f"**Cash-on-Cash Return:** {coc_return:.2%}")

# Commercial property depreciation tax benefits
if property_type.startswith("Commercial"):
    st.header("Depreciation Tax Benefits")
    
    # Create columns for tax benefit display
    tax_col1, tax_col2, tax_col3 = st.columns(3)
    
    with tax_col1:
        st.metric(
            label="Annual Depreciation Deduction", 
            value=f"${annual_depreciation:,.0f}"
        )
        st.caption("Non-cash expense deducted from taxable income")
    
    with tax_col2:
        st.metric(
            label="Tax Savings from Depreciation", 
            value=f"${depreciation_tax_shield:,.0f}",
            delta=f"{depreciation_tax_shield/annual_depreciation*100:.1f}%"
        )
        st.caption(f"At {tax*100:.0f}% tax rate")
    
    with tax_col3:
        st.metric(
            label="After-Tax Cash Flow", 
            value=f"${cash_flow_with_tax_benefits:,.0f}",
            delta=f"{depreciation_tax_shield:,.0f}"
        )
        st.caption("Cash flow with tax benefits")
    
    # Improved explanation with better percentage handling
    if cash_flow <= 0:
        st.info(
            "Depreciation is a non-cash expense that significantly improves commercial property returns. "
            f"For this {property_type.split(' - ')[1]} property, the annual depreciation tax benefit of "
            f"${depreciation_tax_shield:,.0f} transforms a negative or break-even cash flow into a positive return."
        )
    elif depreciation_tax_shield > cash_flow * 10:
        st.info(
            "Depreciation is a non-cash expense that significantly improves commercial property returns. "
            f"For this {property_type.split(' - ')[1]} property, the annual depreciation tax benefit of "
            f"${depreciation_tax_shield:,.0f} is substantially larger than the pre-tax cash flow of ${cash_flow:,.0f}."
        )
    else:
        percentage = min(1000, (depreciation_tax_shield/cash_flow)*100)
        st.info(
            "Depreciation is a non-cash expense that significantly improves commercial property returns. "
            f"For this {property_type.split(' - ')[1]} property, the annual depreciation tax benefit of "
            f"${depreciation_tax_shield:,.0f} increases the effective cash flow by {percentage:.0f}%."
        )

# Property location map below the summary (full width) - Only load when requested
if use_map:
    st.subheader("Property Location")
    
    # Button to load map data (defers loading until explicitly requested)
    load_map = st.button("Load Map and Neighborhood Data")
    
    if load_map:
        with st.spinner("Loading map and neighborhood data..."):
            location_text = ""
            coordinates_text = ""
            
            try:
                # Use cached function to get location data
                location_data = get_location_data(zip_code)
                
                if location_data and len(location_data) > 0:
                    lat = float(location_data[0]["lat"])
                    lon = float(location_data[0]["lon"])
                    place = location_data[0].get("display_name", "").split(",")[0]
                    location_text = f"Location: {place}"
                    coordinates_text = f"Coordinates: {lat:.5f}, {lon:.5f}"
                    
                    # Create map
                    m = folium.Map(location=[lat, lon], zoom_start=13)
                    folium.Marker(
                        [lat, lon],
                        tooltip=f"ZIP Code: {zip_code}",
                        icon=folium.Icon(color="red", icon="home")
                    ).add_to(m)
                    
                    # Add a circle representing 1-mile radius
                    folium.Circle(
                        radius=1609,  # 1 mile in meters
                        location=[lat, lon],
                        color="blue",
                        fill=True,
                        fill_opacity=0.1
                    ).add_to(m)
                    
                    # Fetch amenities from OpenStreetMap using Overpass API - OPTIMIZED BATCH APPROACH
                    # This will search for various amenities within a 1 mile (1609m) radius of the property
                    amenities_to_check = {
                        # Essential amenities
                        "grocery": ["shop=supermarket", "shop=convenience"],
                        "restaurant": ["amenity=restaurant", "amenity=cafe", "amenity=fast_food"],
                        "school": ["amenity=school", "amenity=kindergarten", "amenity=college", "amenity=university"],
                        "transit": ["highway=bus_stop", "railway=station", "railway=tram_stop", "amenity=bus_station"],
                        "park": ["leisure=park", "leisure=garden", "leisure=playground"],
                        
                        # Other useful amenities
                        "health": ["amenity=hospital", "amenity=clinic", "amenity=doctors", "amenity=pharmacy"],
                        "shopping": ["shop=mall", "shop=department_store", "shop=clothing"],
                        "finance": ["amenity=bank", "amenity=atm"],
                        "entertainment": ["amenity=cinema", "amenity=theatre", "leisure=sports_centre", "leisure=fitness_centre"]
                    }
                    
                    # Prepare to store counts of each amenity type
                    amenity_counts = {}
                    amenity_icons = {}
                    
                    # Define icon styles for different amenity types
                    icon_styles = {
                        "grocery": {"icon": "shopping-cart", "color": "green"},
                        "restaurant": {"icon": "cutlery", "color": "red"},
                        "school": {"icon": "graduation-cap", "color": "blue"},
                        "transit": {"icon": "bus", "color": "purple"},
                        "park": {"icon": "tree", "color": "green"},
                        "health": {"icon": "plus-square", "color": "red"},
                        "shopping": {"icon": "shopping-bag", "color": "cadetblue"},
                        "finance": {"icon": "usd", "color": "darkblue"},
                        "entertainment": {"icon": "ticket", "color": "orange"}
                    }
                    
                    # Initialize count for each category
                    for category in amenities_to_check:
                        amenity_counts[category] = 0
                        amenity_icons[category] = icon_styles.get(category, {"icon": "circle", "color": "gray"})
                    
                    # OPTIMIZATION: Batch amenity queries to reduce API calls
                    with st.spinner("Fetching neighborhood amenities..."):
                        # Prepare a single list of all query key-value pairs
                        all_queries = []
                        for category, queries in amenities_to_check.items():
                            for query in queries:
                                key, value = query.split("=")
                                all_queries.append((key, value))
                        
                        # Make a single batch request for all amenities
                        amenity_data = fetch_amenities_batch(lat, lon, all_queries)
                        
                        # Process the results
                        if "elements" in amenity_data:
                            for element in amenity_data["elements"]:
                                # Determine which category this element belongs to
                                for category, queries in amenities_to_check.items():
                                    for query in queries:
                                        key, value = query.split("=")
                                        if key in element.get("tags", {}) and element["tags"][key] == value:
                                            # Count it for this category
                                            amenity_counts[category] += 1
                                            
                                            # Get coordinates for marker
                                            if "lat" in element and "lon" in element:
                                                marker_lat = element["lat"]
                                                marker_lon = element["lon"]
                                            elif "center" in element:
                                                marker_lat = element["center"]["lat"]
                                                marker_lon = element["center"]["lon"]
                                            else:
                                                # Skip elements without location info
                                                continue
                                            
                                            # Get name if available
                                            name = element.get("tags", {}).get("name", f"{value.capitalize()}")
                                            
                                            # Add marker to map
                                            folium.Marker(
                                                [marker_lat, marker_lon],
                                                tooltip=name,
                                                icon=folium.Icon(
                                                    color=amenity_icons[category]["color"],
                                                    icon=amenity_icons[category]["icon"],
                                                    prefix='fa'
                                                )
                                            ).add_to(m)
                                            
                                            # Once matched, no need to check other categories
                                            break
                                    else:
                                        # Continue if the inner loop wasn't broken
                                        continue
                                    # Break the outer loop if inner loop was broken
                                    break
                    
                    # Display the map
                    folium_static(m)
                    
                    # Show location data only (no financial info)
                    st.caption(location_text)
                    st.caption(coordinates_text)
                    
                    # Display amenity counts and calculate walkability score
                    st.subheader("Neighborhood Amenities Analysis")
                    
                    # Create a DataFrame for visualization
                    amenities_df = pd.DataFrame({
                        "Category": list(amenity_counts.keys()),
                        "Count": list(amenity_counts.values())
                    })
                    
                    # Sort by count in descending order
                    amenities_df = amenities_df.sort_values("Count", ascending=False)
                    
                    # Calculate walkability score based on amenity counts (simplified algorithm)
                    # The actual Walk Score algorithm is proprietary, but we can create a simplified version
                    
                    # Weights for different categories (sum should be 1.0)
                    category_weights = {
                        "grocery": 0.2,
                        "restaurant": 0.15,
                        "transit": 0.2,
                        "school": 0.1,
                        "park": 0.1,
                        "health": 0.1,
                        "shopping": 0.05,
                        "finance": 0.05,
                        "entertainment": 0.05
                    }
                    
                    # Score thresholds for each category (number of amenities for a perfect score in that category)
                    score_thresholds = {
                        "grocery": 3,
                        "restaurant": 5,
                        "transit": 5,
                        "school": 2,
                        "park": 2,
                        "health": 3,
                        "shopping": 3,
                        "finance": 2,
                        "entertainment": 2
                    }
                    
                    # Calculate individual category scores
                    category_scores = {}
                    for category, count in amenity_counts.items():
                        threshold = score_thresholds.get(category, 3)
                        # Score is capped at 100 points per category
                        category_scores[category] = min(100, (count / threshold) * 100)
                    
                    # Calculate overall walkability score
                    walkability_score = 0
                    for category, score in category_scores.items():
                        weight = category_weights.get(category, 0.1)
                        walkability_score += score * weight
                    
                    # Round to nearest whole number
                    walkability_score = round(walkability_score)
                    
                    # Create a transit score based on transit amenities
                    transit_score = min(100, category_scores.get("transit", 0) * 1.2)
                    transit_score = round(transit_score)
                    
                    # Create a bike score (simplified - in reality would include hill data, bike lanes, etc.)
                    # This is a simple placeholder that combines transit and parks as proxies for bike-friendliness
                    bike_score = min(100, (category_scores.get("transit", 0) * 0.5 + 
                                          category_scores.get("park", 0) * 0.8))
                    bike_score = round(bike_score)
                    
                    # Display walkability metrics
                    st.subheader("Neighborhood Livability Metrics")
                    
                    # Create columns for various metrics
                    walk_col1, walk_col2, walk_col3 = st.columns(3)
                    
                    with walk_col1:
                        # Determine color based on score
                        if walkability_score >= 70:
                            walk_color = "green"
                            walk_desc = "Very Walkable"
                        elif walkability_score >= 50:
                            walk_color = "orange"
                            walk_desc = "Somewhat Walkable"
                        else:
                            walk_color = "red"
                            walk_desc = "Car-Dependent"
                            
                        st.markdown(f"### <span style='color:{walk_color}'>{walkability_score}</span>", unsafe_allow_html=True)
                        st.markdown("**Walk Score**")
                        st.caption(walk_desc)
                        st.caption("Based on proximity to amenities")
                    
                    with walk_col2:
                        # Determine color based on score
                        if transit_score >= 70:
                            transit_color = "green"
                            transit_desc = "Excellent Transit"
                        elif transit_score >= 50:
                            transit_color = "orange"
                            transit_desc = "Good Transit"
                        else:
                            transit_color = "red"
                            transit_desc = "Limited Transit"
                            
                        st.markdown(f"### <span style='color:{transit_color}'>{transit_score}</span>", unsafe_allow_html=True)
                        st.markdown("**Transit Score**")
                        st.caption(transit_desc)
                        st.caption("Based on public transportation")
                    
                    with walk_col3:
                        # Determine color based on score
                        if bike_score >= 70:
                            bike_color = "green"
                            bike_desc = "Very Bikeable"
                        elif bike_score >= 50:
                            bike_color = "orange"
                            bike_desc = "Bikeable"
                        else:
                            bike_color = "red"
                            bike_desc = "Not Bikeable"
                            
                        st.markdown(f"### <span style='color:{bike_color}'>{bike_score}</span>", unsafe_allow_html=True)
                        st.markdown("**Bike Score**")
                        st.caption(bike_desc)
                        st.caption("Based on bike-friendly factors")
                    
                    # Add a note about the data source
                    st.caption("Note: These scores are calculated based on OpenStreetMap data within a 1-mile radius.")
                    
                    # Display amenity counts visualization
                    st.subheader("Nearby Amenities")
                    
                    # Plot the amenity counts as a bar chart
                    fig_amenities = px.bar(
                        amenities_df,
                        x="Category",
                        y="Count",
                        color="Count",
                        color_continuous_scale="Viridis",
                        title="Amenities within 1 mile radius"
                    )
                    st.plotly_chart(fig_amenities, use_container_width=True)
                    
                    # Add summary about the neighborhood
                    # Identify the top 3 categories with highest counts
                    top_categories = amenities_df.head(3)["Category"].tolist()
                    top_categories_text = ", ".join(top_categories)
                    
                    st.info(f"This neighborhood is particularly well-served with: {top_categories_text}")
                    
                    # Add the neighborhood to the PDF report
                    # This variable will be used in the PDF creation function
                    has_neighborhood_data = True
                    
                else:
                    st.warning(f"Could not find location for ZIP code {zip_code}")
                    st.info("You can still continue with your analysis without the map.")
                    has_neighborhood_data = False
            except Exception as e:
                st.error(f"Error loading map: {str(e)}")
                st.info("You can still continue with your analysis without the map.")
                has_neighborhood_data = False
    else:
        st.info("Click 'Load Map and Neighborhood Data' to view property location and amenities. This helps prevent delays when changing other parameters.")

# Market Data Analysis
if use_fred and fred_data:
    st.header("Market Data Analysis")
    st.subheader("Economic Indicators (FRED)")
    
    fred_col1, fred_col2, fred_col3 = st.columns(3)
    
    # Display current mortgage rate
    if "MORTGAGE30US" in fred_data:
        with fred_col1:
            try:
                value = float(fred_data["MORTGAGE30US"]["value"])
                st.metric(
                    label="Current 30-Year Mortgage Rate",
                    value=f"{value:.2f}%",
                    delta=f"{value - rate*100:.2f}%" if value - rate*100 != 0 else None,
                    delta_color="inverse"  # Lower is better for mortgage rates
                )
                st.caption(f"Source: FRED as of {fred_data['MORTGAGE30US']['date']}")
                
                if value > rate*100:
                    st.info(f"Your loan rate ({rate*100:.2f}%) is better than the current market rate.")
                elif value < rate*100:
                    st.info(f"Current market rates are lower than your loan rate ({rate*100:.2f}%). Refinancing might be beneficial.")
            except (ValueError, KeyError):
                st.metric(label="Current 30-Year Mortgage Rate", value="Data unavailable")
    
    # Display home price index
    if "CSUSHPISA" in fred_data:
        with fred_col2:
            try:
                value = float(fred_data["CSUSHPISA"]["value"])
                st.metric(
                    label="Case-Shiller Home Price Index",
                    value=f"{value:.1f}"
                )
                st.caption(f"Source: FRED as of {fred_data['CSUSHPISA']['date']}")
            except (ValueError, KeyError):
                st.metric(label="Case-Shiller Home Price Index", value="Data unavailable")
    
    # Display rental vacancy rate
    if "RRVRUSQ156N" in fred_data:
        with fred_col3:
            try:
                value = float(fred_data["RRVRUSQ156N"]["value"])
                st.metric(
                    label="Rental Vacancy Rate",
                    value=f"{value:.1f}%"
                )
                st.caption(f"Source: FRED as of {fred_data['RRVRUSQ156N']['date']}")
                
                # Add context for vacancy rate
                if value < 5:
                    st.info("Low vacancy rates typically indicate strong rental demand.")
                elif value > 8:
                    st.info("Higher vacancy rates may indicate increased competition for tenants.")
            except (ValueError, KeyError):
                st.metric(label="Rental Vacancy Rate", value="Data unavailable")
    
    # Display commercial-specific metrics if applicable
    if property_type.startswith("Commercial"):
        st.subheader("Commercial Real Estate Metrics")
        com_col1, com_col2 = st.columns(2)
        
        # Display Commercial Property Price Index
        if "COMPRMS" in fred_data:
            with com_col1:
                try:
                    value = float(fred_data["COMPRMS"]["value"])
                    st.metric(
                        label="Commercial Property Price Index",
                        value=f"{value:.1f}"
                    )
                    st.caption(f"Source: FRED as of {fred_data['COMPRMS']['date']}")
                except (ValueError, KeyError):
                    st.metric(label="Commercial Property Price Index", value="Data unavailable")
        
        # Display Vacant Housing Units (showing raw number)
        if "EVACANTUSQ176N" in fred_data:
            with com_col2:
                try:
                    value = float(fred_data["EVACANTUSQ176N"]["value"])
                    st.metric(
                        label="Vacant Housing Units",
                        value=f"{value:.0f}K"
                    )
                    st.caption(f"Source: FRED as of {fred_data['EVACANTUSQ176N']['date']}")
                    st.caption("Measured in thousands of units")
                except (ValueError, KeyError):
                    st.metric(label="Vacant Housing Units", value="Data unavailable")

# Financial Analysis Section
st.header("Financial Analysis")

# Create projected cash flows for IRR calculation
cash_flows = []
cash_flows.append(-price * down_pct)  # Initial investment (down payment)

annual_cash_flows = []
annual_appreciation = []
cumulative_returns = []
cumulative_value = 0

for year in range(1, years + 1):
    # Assume rent increases by 2% per year
    year_rent = annual_rent * (1 + 0.02)**(year-1)
    year_vacancy_loss = year_rent * vacancy
    year_effective_income = year_rent - year_vacancy_loss
    year_expenses = year_effective_income * expenses
    year_noi = year_effective_income - year_expenses
    year_cash_flow = year_noi - annual_mortgage
    
    # Tax calculations with enhanced depreciation benefits
    if property_type.startswith("Commercial"):
        # Use different depreciation schedules based on property type
        if commercial_type == "multifamily":
            depr_period = 27.5  # Residential rate for multifamily
            building_value_ratio = 0.8  # Building value as ratio of purchase price
        else:
            depr_period = 39  # Commercial buildings use 39-year schedule
            building_value_ratio = 0.8
        
        # Calculate annual depreciation
        year_depreciation = price * building_value_ratio / depr_period
    else:
        # Default values for residential properties
        year_depreciation = price * 0.8 / 27.5
    
    # Calculate taxable income with depreciation deduction
    taxable_income = year_noi - annual_mortgage - year_depreciation
    tax_payment = max(0, taxable_income * tax)
    
    # The "tax shield" is the tax savings from depreciation
    year_depreciation_tax_shield = year_depreciation * tax
    
    # Add tax shield to the cash flow
    after_tax_cash_flow = year_cash_flow - tax_payment
    year_cash_flow_with_tax_benefits = after_tax_cash_flow + year_depreciation_tax_shield
    
    cash_flows.append(year_cash_flow_with_tax_benefits)
    annual_cash_flows.append(year_cash_flow_with_tax_benefits)
    
    # Track property value
    property_value = price * (1 + appr)**year
    annual_appreciation.append(property_value)
    
    # Cumulative returns
    cumulative_value += year_cash_flow_with_tax_benefits
    cumulative_returns.append(cumulative_value)

# Add final property sale in the last year
final_property_value = price * (1 + appr)**years
selling_costs = final_property_value * 0.06  # Assume 6% selling costs
loan_balance = 0
if loan_term > years:
    # Calculate remaining loan balance if selling before loan is paid off
    payments_made = years * 12
    remaining_payments = loan_term * 12 - payments_made
    if r > 0:  # Avoid division by zero
        loan_balance = loan * (1 - (1 - (1 + r)**(-n)) / (1 - (1 + r)**(-remaining_payments)))

net_proceeds = final_property_value - selling_costs - loan_balance
# Adjust the last cash flow to include property sale
if cash_flows:
    cash_flows[-1] += net_proceeds

# Calculate IRR
try:
    project_irr = irr(cash_flows)
except:
    project_irr = 0

# Total ROI
total_profit = sum(annual_cash_flows) + (final_property_value - price)
roi = total_profit / (price * down_pct) if price * down_pct > 0 else 0

# Display main metrics
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Cap Rate", f"{cap_rate:.2%}")
    st.metric("Cash-on-Cash Return", f"{coc_return:.2%}")

with col2:
    st.metric("IRR", f"{project_irr:.2%}")
    st.metric("Total ROI", f"{roi:.2%}")

with col3:
    if property_type.startswith("Commercial"):
        st.metric("Cash Flow (After Tax Benefits)", f"${cash_flow_with_tax_benefits:,.0f}")
    else:
        st.metric("Cash Flow (Year 1)", f"${cash_flow:,.0f}")

# Visualization of cash flows and property value over time
st.subheader("Cash Flow & Property Value Projections")

# Create DataFrames for visualization
projection_df = pd.DataFrame({
    "Year": range(1, years + 1),
    "Cash Flow": annual_cash_flows,
    "Property Value": annual_appreciation,
    "Cumulative Returns": cumulative_returns
})

# Cash Flow Projection Chart
fig_cash_flow = px.bar(
    projection_df,
    x="Year",
    y="Cash Flow",
    title="Projected Annual Cash Flow",
    labels={"Cash Flow": "Annual Cash Flow ($)"},
    color_discrete_sequence=["#2C6E49"]
)
fig_cash_flow.update_layout(xaxis_title="Year", yaxis_title="Cash Flow ($)")
st.plotly_chart(fig_cash_flow, use_container_width=True)

# Property Value Projection Chart
fig_value = px.line(
    projection_df,
    x="Year",
    y="Property Value",
    title="Projected Property Value",
    labels={"Property Value": "Estimated Value ($)"},
    color_discrete_sequence=["#4D908E"]
)
fig_value.update_layout(xaxis_title="Year", yaxis_title="Property Value ($)")
st.plotly_chart(fig_value, use_container_width=True)

# Cumulative Returns Chart
fig_returns = px.line(
    projection_df,
    x="Year",
    y="Cumulative Returns",
    title="Cumulative Cash Flow Returns",
    labels={"Cumulative Returns": "Cumulative Returns ($)"},
    color_discrete_sequence=["#F8961E"]
)
fig_returns.update_layout(xaxis_title="Year", yaxis_title="Cumulative Returns ($)")
st.plotly_chart(fig_returns, use_container_width=True)

# Add after the existing financial projections charts

# =========== NEW VISUALIZATIONS ===========
st.header("Advanced Financial Analysis")

# 1. ROI COMPARISON ACROSS SCENARIOS
st.subheader("ROI Comparison Across Scenarios")

# Create dataframe to store ROI calculations for different scenarios
scenario_comparison = pd.DataFrame({
    "Year": range(1, years + 1)
})

# Calculate ROI for current scenario (already selected in UI)
scenario_comparison[f"ROI ({scenario})"] = [0] * years
cumulative_value_current = 0
cumulative_investment = price * down_pct

for i, year in enumerate(range(1, years + 1)):
    # Use the values we already calculated
    cumulative_value_current += annual_cash_flows[i]
    if year == years:
        # Add property sale in final year
        cumulative_value_current += final_property_value - price
    
    # Calculate ROI for each year
    scenario_comparison.at[i, f"ROI ({scenario})"] = cumulative_value_current / cumulative_investment

# Calculate for other scenarios
for alt_scenario in ["Baseline", "Bullish", "Bearish"]:
    if alt_scenario == scenario:
        continue  # Skip current scenario as we already calculated it
    
    scenario_comparison[f"ROI ({alt_scenario})"] = [0] * years
    rent_multiplier = {"Bullish": 1.2, "Baseline": 1.0, "Bearish": 0.8}[alt_scenario]
    alt_rent = base_rent * rent_multiplier
    alt_annual_rent = alt_rent * 12
    
    # Recalculate for alternative scenario
    cumulative_value_alt = 0
    
    for i, year in enumerate(range(1, years + 1)):
        # Assume rent increases by 2% per year
        year_rent = alt_annual_rent * (1 + 0.02)**(year-1)
        year_vacancy_loss = year_rent * vacancy
        year_effective_income = year_rent - year_vacancy_loss
        year_expenses = year_effective_income * expenses
        year_noi = year_effective_income - year_expenses
        year_cash_flow = year_noi - annual_mortgage
        
        # Tax calculations
        if property_type.startswith("Commercial"):
            # Use appropriate depreciation schedule
            if commercial_type == "multifamily":
                depr_period = 27.5
                building_value_ratio = 0.8
            else:
                depr_period = 39
                building_value_ratio = 0.8
            
            year_depreciation = price * building_value_ratio / depr_period
        else:
            year_depreciation = price * 0.8 / 27.5
        
        taxable_income = year_noi - annual_mortgage - year_depreciation
        tax_payment = max(0, taxable_income * tax)
        year_depreciation_tax_shield = year_depreciation * tax
        year_cash_flow_with_tax_benefits = year_cash_flow - tax_payment + year_depreciation_tax_shield
        
        cumulative_value_alt += year_cash_flow_with_tax_benefits
        
        # Add property sale in final year
        if year == years:
            cumulative_value_alt += final_property_value - price
        
        # Calculate ROI
        scenario_comparison.at[i, f"ROI ({alt_scenario})"] = cumulative_value_alt / cumulative_investment

# Create ROI comparison chart
fig_roi_scenarios = px.line(
    scenario_comparison,
    x="Year",
    y=[f"ROI ({s})" for s in ["Baseline", "Bullish", "Bearish"] if f"ROI ({s})" in scenario_comparison.columns],
    title="ROI Comparison Across Scenarios",
    labels={"value": "Return on Investment (ROI)", "variable": "Scenario"},
    color_discrete_sequence=["#2C6E49", "#4D908E", "#F8961E"],
)
fig_roi_scenarios.update_layout(xaxis_title="Year", yaxis_title="ROI", yaxis_tickformat=".0%")
st.plotly_chart(fig_roi_scenarios, use_container_width=True)


# 3. HEATMAP: ROI VS APPRECIATION & INTEREST RATES
st.subheader("ROI Heatmap: Appreciation Rate vs Interest Rate")

# Define ranges for heatmap
heatmap_appreciation = np.linspace(0.01, 0.08, 8)  # 1% to 8% in 8 steps
heatmap_interest = np.linspace(0.03, 0.09, 8)  # 3% to 9% in 8 steps

# Create arrays to store heatmap data
heatmap_data = np.zeros((len(heatmap_appreciation), len(heatmap_interest)))

# Calculate ROI for each combination
for i, appr_rate in enumerate(heatmap_appreciation):
    for j, int_rate in enumerate(heatmap_interest):
        # Calculate mortgage payment with this interest rate
        r_monthly = int_rate / 12
        heatmap_mortgage = loan * (r_monthly * (1 + r_monthly)**n) / ((1 + r_monthly)**n - 1) if loan > 0 and r_monthly > 0 else 0
        annual_heatmap_mortgage = heatmap_mortgage * 12
        
        # Initialize cash flows
        hm_cash_flows = []
        hm_cash_flows.append(-price * down_pct)  # Initial investment
        
        # Calculate yearly cash flows
        for year in range(1, years + 1):
            # Current year rent (with 2% annual increase)
            year_rent = annual_rent * (1 + 0.02)**(year-1)
            year_vacancy_loss = year_rent * vacancy
            year_effective_income = year_rent - year_vacancy_loss
            year_expenses = year_effective_income * expenses
            year_noi = year_effective_income - year_expenses
            year_cash_flow = year_noi - annual_heatmap_mortgage
            
            # Tax calculations with this depreciation
            if property_type.startswith("Commercial"):
                # Use appropriate depreciation schedule
                if commercial_type == "multifamily":
                    depr_period = 27.5
                    building_value_ratio = 0.8
                else:
                    depr_period = 39
                    building_value_ratio = 0.8
                
                year_depreciation = price * building_value_ratio / depr_period
            else:
                year_depreciation = price * 0.8 / 27.5
            
            taxable_income = year_noi - annual_heatmap_mortgage - year_depreciation
            tax_payment = max(0, taxable_income * tax)
            year_depreciation_tax_shield = year_depreciation * tax
            year_cash_flow_with_tax_benefits = year_cash_flow - tax_payment + year_depreciation_tax_shield
            
            hm_cash_flows.append(year_cash_flow_with_tax_benefits)
        
        # Add property sale with this appreciation rate
        final_value = price * (1 + appr_rate)**years
        selling_costs = final_value * 0.06
        loan_balance = 0
        if loan_term > years:
            # Calculate remaining loan balance
            payments_made = years * 12
            remaining_payments = loan_term * 12 - payments_made
            if r_monthly > 0:
                loan_balance = loan * (1 - (1 - (1 + r_monthly)**(-n)) / (1 - (1 + r_monthly)**(-remaining_payments)))
        
        net_proceeds = final_value - selling_costs - loan_balance
        hm_cash_flows[-1] += net_proceeds
        
        # Calculate IRR
        try:
            hm_irr = irr(hm_cash_flows)
            heatmap_data[i, j] = hm_irr * 100  # Convert to percentage for display
        except:
            heatmap_data[i, j] = 0
        
# Create heatmap
fig_heatmap = px.imshow(
    heatmap_data,
    x=[f"{rate:.1f}%" for rate in heatmap_interest * 100],
    y=[f"{rate:.1f}%" for rate in heatmap_appreciation * 100],
    color_continuous_scale="Viridis",
    title="ROI Heatmap: Appreciation Rate vs Interest Rate",
    labels={
        "x": "Interest Rate",
        "y": "Appreciation Rate",
        "color": "IRR (%)"
    }
)
fig_heatmap.update_layout(
    xaxis_title="Interest Rate",
    yaxis_title="Appreciation Rate"
)
st.plotly_chart(fig_heatmap, use_container_width=True)

# Add a download PDF button at the bottom of the page
st.header("Generate Report")
st.write("Click the button below to generate a detailed PDF report of this analysis.")

custom_notes = st.text_area("Add Custom Notes to Report (Optional)", 
                           placeholder="Enter any additional notes or commentary for the PDF report...")

if st.button("Generate PDF Report"):
    with st.spinner("Generating PDF report..."):
        try:
            pdf_buffer = create_pdf_report()
            st.success("PDF Report Generated Successfully!")
            st.download_button(
                label="Download PDF Report",
                data=pdf_buffer,
                file_name=f"real_estate_analysis_{zip_code}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.error(f"Failed to generate PDF: {str(e)}")
            st.info("Try adjusting your inputs or check for any errors above.")