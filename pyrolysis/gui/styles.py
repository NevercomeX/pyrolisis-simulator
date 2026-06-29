import streamlit as st

def apply_custom_styles():
    """Applies custom theme-aware styling to the Streamlit dashboard."""
    st.markdown("""
        <style>
        .main {
            background-color: var(--background-color);
        }
        .stMetric {
            background-color: var(--secondary-background-color) !important;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid rgba(128, 128, 128, 0.2) !important;
        }
        .stAlert {
            border-radius: 10px;
        }
        .reportview-container .main .block-container{
            padding-top: 2rem;
        }
        h1, h2, h3, h4, h5, h6 {
            color: var(--text-color);
            font-family: 'Outfit', 'Inter', sans-serif;
        }
        .sidebar-text {
            font-size: 14px;
            color: var(--text-color);
            opacity: 0.8;
        }
        </style>
    """, unsafe_allow_html=True)
