import streamlit as st
import pandas as pd
import requests
import json
import uuid
from datetime import datetime, timedelta

st.set_page_config(page_title="Chivent - Chicago Events", layout="wide")
TICKETMASTER_API_KEY = "pmbdy5uLSZnpbGGenJyLkA7xeRCPS20L"

# Initialize session state variables
if 'user_id' not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if 'page' not in st.session_state:
    st.session_state.page = 'home'

if 'selected_event' not in st.session_state:
    st.session_state.selected_event = None

if 'current_api_page' not in st.session_state:
    st.session_state.current_api_page = 0

if 'events_cache' not in st.session_state:
    st.session_state.events_cache = {}

# Initialize in-memory cache with expiration
if 'api_cache' not in st.session_state:
    st.session_state.api_cache = {}

if 'cart' not in st.session_state:
    st.session_state.cart = []

# Navigation control functions
def go_to_home():
    st.session_state.page = 'home'

def go_to_event_details(event_id):
    st.session_state.selected_event = event_id
    st.session_state.page = 'event_details'

def go_to_cart():
    st.session_state.page = 'cart'

def next_page():
    st.session_state.current_api_page += 1

def prev_page():
    if st.session_state.current_api_page > 0:
        st.session_state.current_api_page -= 1

def fetch_events_from_api(page=0, size=20):
    cache_key = f"events_page_{page}_size_{size}"
    
    # Check if we have a valid cache entry
    if cache_key in st.session_state.api_cache:
        cache_entry = st.session_state.api_cache[cache_key]
        # Check if cache is still valid (less than 1 hour old)
        if datetime.now() < cache_entry['expiry']:
            return cache_entry['data']
    
    # If no valid cache, call the API
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "city": "Chicago",
        "stateCode": "IL",
        "size": size,
        "page": page,
        "sort": "date,asc"
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        st.session_state.api_cache[cache_key] = {
            'data': data,
            'expiry': datetime.now() + timedelta(hours=1)
        }
        
        return data
    except Exception as e:
        st.error(f"Error fetching events from Ticketmaster API: {e}")
        if cache_key in st.session_state.api_cache:
            return st.session_state.api_cache[cache_key]['data']
        return {"_embedded": {"events": []}}

def process_events(api_data):
    if "_embedded" not in api_data or "events" not in api_data["_embedded"]:
        return []
    
    events = []
    filtered_count = 0
    
    for event in api_data["_embedded"]["events"]:
        # Check for price information
        has_price = False
        price = "N/A"
        price_value = 0.0
        if "priceRanges" in event and event["priceRanges"]:
            min_price = event["priceRanges"][0].get("min")
            if min_price is not None:
                has_price = True
                price_value = float(min_price)
                price = f"${price_value:.2f}"
        
        # Check for image
        has_image = False
        image_url = "https://via.placeholder.com/300x200?text=Event+Image"
        if "images" in event and event["images"]:
            has_image = True
            suitable_images = [img for img in event["images"] if img.get("width", 0) >= 300]
            if suitable_images:
                image_url = suitable_images[0]["url"]
            elif event["images"]:
                image_url = event["images"][0]["url"]
        
        # Check for description
        has_description = False
        description = "No description available."
        
        if "info" in event and event["info"] and len(event["info"].strip()) > 10:
            has_description = True
            description = event["info"]
        elif "pleaseNote" in event and event["pleaseNote"] and len(event["pleaseNote"].strip()) > 10:
            has_description = True
            description = event["pleaseNote"]
        elif "description" in event and event["description"] and len(event["description"].strip()) > 10:
            has_description = True
            description = event["description"]
        
        if not (has_image and has_price):
            filtered_count += 1
            continue
        
        # Extract venue info
        venue = "Chicago, IL"
        if "_embedded" in event and "venues" in event["_embedded"] and event["_embedded"]["venues"]:
            venue_name = event["_embedded"]["venues"][0].get("name", "")
            city = event["_embedded"]["venues"][0].get("city", {}).get("name", "Chicago")
            state = event["_embedded"]["venues"][0].get("state", {}).get("stateCode", "IL")
            venue = f"{venue_name}, {city}, {state}"
        
        # Extract date and time
        start_date = "TBA"
        start_time = "TBA"
        end_time = "TBA"
        
        if "dates" in event and "start" in event["dates"]:
            if "localDate" in event["dates"]["start"]:
                start_date = event["dates"]["start"]["localDate"]
            
            if "localTime" in event["dates"]["start"]:
                start_time = event["dates"]["start"]["localTime"]
                hour, minute = map(int, start_time.split(':')[:2])
                end_hour = (hour + 3) % 24
                end_time = f"{end_hour:02d}:{minute:02d}:00"
        
        processed_event = {
            "id": event["id"],
            "title": event["name"],
            "description": description,
            "image": image_url,
            "price": price,
            "price_value": price_value,
            "location": venue,
            "startDate": start_date,
            "startTime": start_time,
            "endTime": end_time,
            "url": event.get("url", ""),
            "has_price": has_price,
            "has_description": has_description,
            "has_image": has_image
        }
        
        events.append(processed_event)
    
    if 'filtered_count' not in st.session_state:
        st.session_state.filtered_count = 0
    st.session_state.filtered_count = filtered_count
    return events

def fetch_enough_events(target_count=20, max_pages=5):
    events = []
    page = st.session_state.current_api_page
    filtered_count = 0
    pages_tried = 0
    
    while len(events) < target_count and pages_tried < max_pages:
        api_data = fetch_events_from_api(page, size=50)  # Fetch more events per page
        new_events = process_events(api_data)
        
        if 'filtered_count' in st.session_state:
            filtered_count += st.session_state.filtered_count
        events.extend(new_events)
        
        if not new_events and "_embedded" in api_data and "events" in api_data["_embedded"] and not api_data["_embedded"]["events"]:
            break
        
        page += 1
        pages_tried += 1
    
    st.session_state.filtered_count = filtered_count
    
    return events[:target_count]

# Add an event to the cart
def add_to_cart(event):
    event_data = {
        'event_id': event['id'],
        'title': event['title'],
        'price': event['price'],
        'price_value': event['price_value'],
        'quantity': 1
    }
    # Check if item already exists in cart
    existing_item = next((item for item in st.session_state.cart if item['event_id'] == event['id']), None)
    
    if existing_item:
        existing_item['quantity'] += 1
    else:
        st.session_state.cart.append(event_data)

# Remove an event from the cart
def remove_from_cart(event_id):
    st.session_state.cart = [item for item in st.session_state.cart if item['event_id'] != event_id]

def format_date(date_str):
    if date_str == "TBA":
        return "TBA"
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        return date_obj.strftime("%B %d, %Y")
    except:
        return date_str

# Format time for display
def format_time(time_str):
    if time_str == "TBA":
        return "TBA"
    try:
        time_obj = datetime.strptime(time_str, "%H:%M:%S")
        return time_obj.strftime("%I:%M %p")
    except:
        return time_str

def display_events():
    st.title("Upcoming Events in Chicago")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.button("Previous Page", on_click=prev_page, disabled=(st.session_state.current_api_page <= 0))
    
    with col2:
        st.button("Next Page", on_click=next_page)
    
    st.write(f"Page {st.session_state.current_api_page + 1}")
    
    events = fetch_enough_events(target_count=20)
    
    if not events:
        st.warning("No events found for this page. Try another page or check back later.")
        return
    
    for event in events:
        st.session_state.events_cache[event['id']] = event
    
    
    # Create three columns for event display
    cols = st.columns(3)
    
    for i, event in enumerate(events):
        with cols[i % 3]:
            with st.container():
                # Image
                st.image(event["image"], use_column_width=True)
                
                # Title
                st.subheader(event["title"])
                
                # Truncate description if too long
                desc = event["description"]
                if len(desc) > 100:
                    desc = desc[:100] + "..."
                
                st.write(desc)
                st.write(f"**Price:** {event['price']}")
                st.write(f"**Location:** {event['location']}")
                st.write(f"**Date:** {format_date(event['startDate'])}")
                st.write(f"**Time:** {format_time(event['startTime'])} - {format_time(event['endTime'])}")
                
                # Button to view event details
                st.button(
                    "View Details", 
                    key=f"view_{event['id']}", 
                    on_click=go_to_event_details, 
                    args=(event['id'],)
                )
                st.markdown("---")

# Display details for a single event
def display_event_details():
    event_id = st.session_state.selected_event
    event = st.session_state.events_cache.get(event_id)
    
    if not event:
        st.error("Event not found! It may have been removed or the page was refreshed.")
        st.button("Back to Events", on_click=go_to_home)
        return
    
    # Back button
    st.button("← Back to Events", on_click=go_to_home)
    
    st.title(event["title"])
    
    completeness = []
    if event.get('has_description', False): completeness.append("Detailed description available")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.image(event["image"], use_column_width=True)
        st.write(f"**Price:** {event['price']}")
        
        # Buttons for actions
        if st.button("Add to Cart", key=f"add_cart_{event_id}"):
            add_to_cart(event)
            st.success("Added to cart!")
    
    with col2:
        st.write("### Event Information")
        st.write(event["description"])
        st.write(f"**Location:** {event['location']}")
        st.write(f"**Date:** {format_date(event['startDate'])}")
        st.write(f"**Time:** {format_time(event['startTime'])} - {format_time(event['endTime'])}")
        

# Display shopping cart
def display_cart():
    st.title("Your Cart")
    
    cart_items = st.session_state.cart
    
    if not cart_items:
        st.write("Your cart is empty.")
        st.button("Browse Events", on_click=go_to_home)
        return
    
    total = 0
    # Display cart items
    for item in cart_items:
        event_id = item['event_id']
        
        event = st.session_state.events_cache.get(event_id)
        
        if not event:
            event = {
                "title": item.get("title", "Unknown Event"),
                "price": item.get("price", "N/A"),
                "price_value": item.get("price_value", 0.0)
            }
        
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            st.subheader(event["title"])
            st.write(f"**Price:** {event['price']}")
            st.write(f"**Quantity:** {item['quantity']}")
        
        with col2:
            # Calculate item total
            price_value = item.get('price_value', 0.0)
            item_total = price_value * item['quantity']
            st.write(f"**Item Total:** ${item_total:.2f}")
            total += item_total
        
        with col3:
            # Remove item button
            btn_key = f"remove_{item['event_id']}"
            if st.button("Remove", key=btn_key):
                remove_from_cart(item['event_id'])
                st.experimental_rerun()  
        
        st.markdown("---")
    
    st.subheader(f"Total: ${total:.2f}")
    
    # Checkout button
    if st.button("Checkout"):
        st.success("Thank you for your purchase! (This is a demo, no actual purchase was made)")
        # Clear cart
        st.session_state.cart = []
        st.button("Return to Events", on_click=go_to_home)

# Custom CSS 
def apply_custom_css():
    st.markdown("""
    <style>
    .main {
        padding: 1rem;
    }
    
    .stButton>button {
        width: 100%;
        background-color: #FF4B4B;
        color: white;
        border: none;
    }
    
    .stButton>button:hover {
        background-color: #E03131;
    }
    
    h1, h2, h3 {
        color: #FF4B4B;
    }
    
    .sidebar .sidebar-content {
        background-color: #F8F9FA;
    }
    
    /* Improve card layout */
    .stContainer {
        background-color: #f9f9f9;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    </style>
    """, unsafe_allow_html=True)


def main():
    apply_custom_css()
    
    # Navigation menu
    st.sidebar.title("Chivent")
    st.sidebar.write("Chicago's Events")
    
    if st.sidebar.button("Browse Events"):
        go_to_home()
    
    if st.sidebar.button("Your Cart"):
        go_to_cart()
    
    # Display cart count in sidebar
    cart_count = sum(item['quantity'] for item in st.session_state.cart)
    st.sidebar.write(f"Cart Items: {cart_count}")
    st.sidebar.markdown("---")
    
    # Handle different pages
    if st.session_state.page == 'home':
        display_events()
    elif st.session_state.page == 'event_details':
        display_event_details()
    elif st.session_state.page == 'cart':
        display_cart()

if __name__ == "__main__":
    main()