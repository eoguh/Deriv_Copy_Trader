import os
import MetaTrader5 as mt5

# Initialize the MetaTrader 5 terminal
if not mt5.initialize():
    print("initialize() failed, error code =", mt5.last_error())
    quit()

# Define source and destination account login details
source_account = {"login": os.getenv("SOURCE_ACCOUNT_NUMBER"), "password": os.getenv("SOURCE_ACCOUNT_PASSWORD1"), "server": "server_name"}
destination_accounts = [
    {"login": os.getenv("DESTINATION_ACCOUNT_NUMBER1"), "password": os.getenv("DESTINATION_ACCOUNT_PASSWORD1"), "server": "server_name"},
    # {"login": 111222, "password": "destination_password2", "server": "server_name"}
]

# Function to connect to an account
def connect_to_account(account):
    if not mt5.login(account["login"], account["password"], account["server"]):
        print(f"Failed to connect to account {account['login']}, error code =", mt5.last_error())
        return False
    return True

# Function to copy trade
def copy_trade(trade, account):
    connect_to_account(account)
    symbol = trade.symbol
    lot_size = calculate_lot_size(trade.volume, account)
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": trade.type,
        "price": mt5.symbol_info_tick(symbol).bid,
        "sl": trade.sl,
        "tp": trade.tp,
        "deviation": 20,
        "magic": 234000,
        "comment": "Copied trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Failed to execute trade on account {account['login']}, retcode =", result.retcode)

# Function to calculate lot size based on destination account balance
def calculate_lot_size(source_lot_size, destination_account):
    source_balance = mt5.account_info().balance
    destination_balance = mt5.account_info().balance
    return (source_lot_size * destination_balance) / source_balance

# Connect to source account
connect_to_account(source_account)

# Monitor trades and copy them to destination accounts
while True:
    trades = mt5.positions_get()
    for trade in trades:
        for account in destination_accounts:
            copy_trade(trade, account)

# Shutdown MetaTrader 5 terminal
mt5.shutdown()
