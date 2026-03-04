import streamlit as st
import pandas as pd
from datetime import datetime
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Initialize Supabase
@st.cache_resource
def init_supabase():
    if SUPABASE_URL and SUPABASE_KEY:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    return None

supabase = init_supabase()

# Page config
st.set_page_config(
    page_title="CHOPBAR Admin Panel",
    page_icon="✂️",
    layout="wide"
)

# Title
st.title("✂️ CHOPBAR - Admin Dashboard")

# Function to load data
def load_data():
    if supabase:
        try:
            response = supabase.table("bookings").select("*").order("created_at", desc=True).execute()
            return response.data
        except Exception as e:
            st.error(f"Error fetching data from Supabase: {e}")
            return []
    else:
        st.error("Supabase credentials not found in .env")
        return []

def load_barbershop_data():
    import json
    if os.path.exists('data/barbershop.json'):
        with open('data/barbershop.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

# Sidebar
st.sidebar.header("Filter Options")

# Load data
bookings = load_data()
shop_data = load_barbershop_data()

# Display Shop Status
if shop_data:
    st.sidebar.subheader("Shop Info")
    st.sidebar.info(f"Services: {len(shop_data.get('services', []))}")
    st.sidebar.info(f"Barbers: {len(shop_data.get('barbers', []))}")

# Main Content
if not bookings:
    st.warning("No bookings found.")
else:
    # Convert to DataFrame for easier handling
    df = pd.DataFrame(bookings)
    
    # Clean up column names for display
    display_columns = ['id', 'date', 'time', 'master', 'service', 'price', 'status', 'telegram_id']
    
    # Filter by Status
    status_filter = st.sidebar.multiselect(
        "Filter by Status",
        options=df['status'].unique(),
        default=df['status'].unique()
    )
    
    # Filter by Master
    master_filter = st.sidebar.multiselect(
        "Filter by Master",
        options=df['master'].unique(),
        default=df['master'].unique()
    )
    
    # Apply filters
    filtered_df = df[
        (df['status'].isin(status_filter)) &
        (df['master'].isin(master_filter))
    ]
    
    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Bookings", len(bookings))
    with col2:
        st.metric("Revenue (Est.)", f"{filtered_df['price'].sum()} ₸")
    with col3:
        st.metric("Active Bookings", len(filtered_df[filtered_df['status'] == 'new']))

    # Display Table
    st.subheader("Bookings List")
    st.dataframe(
        filtered_df[display_columns],
        use_container_width=True,
        hide_index=True
    )

    # Detailed View
    st.subheader("Booking Details")
    selected_id = st.selectbox("Select Booking ID to view details", filtered_df['id'])
    
    if selected_id:
        booking_detail = df[df['id'] == selected_id].iloc[0]
        st.json(booking_detail.to_dict())

# Footer
st.markdown("---")
st.caption("CHOPBAR Admin System v1.0")
