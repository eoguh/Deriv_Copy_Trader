import os
import deriv_api  # Import the Deriv API library 

# Authentication details
api_key = "YOUR_API_KEY"  
api_secret = "YOUR_API_SECRET" 
account_id = "YOUR_ACCOUNT_ID"

# Connect to Deriv API
client = deriv_api.API(api_key, api_secret, account_id) 

# Function to get open positions from a target account (replace with your logic to identify the target trader)
def get_target_open_positions(target_account_id): 
    open_positions = client.get_open_positions(account_id=target_account_id) 
    return open_positions 

# Function to copy a trade from a target account to the current account
def copy_trade(target_position):
    # Extract relevant details from the target position
    instrument = target_position["instrument"]
    direction = target_position["direction"]  # "buy" or "sell"
    amount = target_position["amount"]
    
    # Place the trade on the current account
    if direction == "buy":
        order = client.create_order(instrument=instrument, type="market", direction="buy", amount=amount)
    else:
        order = client.create_order(instrument=instrument, type="market", direction="sell", amount=amount)
    
    return order

# Main loop to continuously monitor and copy trades
while True: 
    target_positions = get_target_open_positions(target_account_id)  
    for position in target_positions:
        copy_trade(position)
    
    # Add a sleep timer if needed to avoid excessive API calls
    time.sleep(5) 