import os
import websocket
import json
import time
from threading import Thread, Event
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DerivMT5CopyTradingBot:
    def __init__(self, source_token, destination_token, source_account_number, destination_account_number, app_id):
        self.source_token = source_token
        self.destination_token = destination_token
        self.source_account_number = source_account_number
        self.destination_account_number = destination_account_number
        self.ws_url = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
        self.source_ws = None
        self.destination_ws = None
        self.should_run = Event()
        self.should_run.set()
        self.ping_interval = 15
        self.reconnect_delay = 5
        self.connection_retries = 3
        self.retry_delay = 5

    def check_connections(self):
        """Check if both WebSocket connections are alive."""
        while self.should_run.is_set():
            try:
                source_connected = self.source_ws and self.source_ws.sock and self.source_ws.sock.connected
                dest_connected = self.destination_ws and self.destination_ws.sock and self.destination_ws.sock.connected
                
                if not source_connected:
                    logger.warning("Source WebSocket connection lost")
                    self.start_source_connection()
                
                if not dest_connected:
                    logger.warning("Destination WebSocket connection lost")
                    self.start_destination_connection()
                    
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                logger.error(f"Error checking connections: {str(e)}")

    def start(self):
        """Start both source and destination WebSocket connections."""
        try:
            self.start_source_connection()
            self.start_destination_connection()
            Thread(target=self.keep_alive_ping, args=(self.source_ws, "source")).start()
            Thread(target=self.keep_alive_ping, args=(self.destination_ws, "destination")).start()
            Thread(target=self.check_connections).start()  # Add connection checker
        except Exception as e:
            logger.error(f"Failed to start copy trading bot: {str(e)}")
            raise

    def start_source_connection(self):
        """Initialize and start source WebSocket connection."""
        self.source_ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_source_open,
            on_message=self.on_source_message,
            on_error=self.on_error,
            on_close=self.on_source_close,
            on_ping=self.on_ping,
            on_pong=self.on_pong
        )
        Thread(target=self._run_websocket, args=(self.source_ws, "source")).start()

    def start_destination_connection(self):
        """Initialize and start destination WebSocket connection."""
        self.destination_ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_destination_open,
            on_message=self.on_destination_message,
            on_error=self.on_error,
            on_close=self.on_destination_close,
            on_ping=self.on_ping,
            on_pong=self.on_pong
        )
        Thread(target=self._run_websocket, args=(self.destination_ws, "destination")).start()

    def _run_websocket(self, ws, name):
        """Run WebSocket connection with automatic reconnection."""
        retries = 0
        while self.should_run.is_set():
            try:
                ws.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    skip_utf8_validation=True  # Add this for better performance
                )
                if self.should_run.is_set():
                    retries += 1
                    if retries <= self.connection_retries:
                        logger.warning(f"WebSocket {name} disconnected. Attempting reconnect {retries}/{self.connection_retries}")
                        time.sleep(self.retry_delay * retries)  # Exponential backoff
                    else:
                        logger.error(f"Max retries reached for {name} WebSocket. Stopping bot.")
                        self.stop()
                        break
            except websocket.WebSocketException as e:
                logger.error(f"WebSocket {name} error: {str(e)}")
                time.sleep(self.reconnect_delay)
            except Exception as e:
                logger.error(f"Unexpected error in {name} WebSocket: {str(e)}")
                time.sleep(self.reconnect_delay)

    def keep_alive_ping(self, ws, name):
        """Send periodic ping to keep connection alive."""
        while self.should_run.is_set():
            try:
                if ws and ws.sock and ws.sock.connected:
                    ping_request = {"ping": 1}
                    ws.send(json.dumps(ping_request))
                    logger.debug(f"Ping sent to {name} WebSocket")
                time.sleep(self.ping_interval)
            except Exception as e:
                logger.error(f"Error sending ping to {name} WebSocket: {str(e)}")
                time.sleep(1)

    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        logger.error(f"WebSocket error: {str(error)}")

    def on_ping(self, ws, message):
        """Handle ping messages."""
        logger.debug(f"Ping received: {message}")
        if ws and ws.sock and ws.sock.connected:
            ws.send(json.dumps({"pong": 1}))

    def on_pong(self, ws, message):
        """Handle pong messages."""
        logger.debug(f"Pong received: {message}")

    def on_source_open(self, ws):
        """Handle source account connection."""
        logger.info("Source account connected")
        self.authorize_account(ws, self.source_token)

    def on_destination_open(self, ws):
        """Handle destination account connection."""
        logger.info("Destination account connected")
        self.authorize_account(ws, self.destination_token)

    def on_source_close(self, ws, close_status_code, close_msg):
        """Handle source WebSocket connection closure."""
        logger.warning(f"Source WebSocket connection closed: {close_msg} ({close_status_code})")
        if self.should_run.is_set():
            Thread(target=self.start_source_connection).start()

    def on_destination_close(self, ws, close_status_code, close_msg):
        """Handle destination WebSocket connection closure."""
        logger.warning(f"Destination WebSocket connection closed: {close_msg} ({close_status_code})")
        if self.should_run.is_set():
            Thread(target=self.start_destination_connection).start()

    def stop(self):
        """Gracefully stop the bot."""
        logger.info("Stopping the bot...")
        self.should_run.clear()
        if self.source_ws:
            self.source_ws.close()
        if self.destination_ws:
            self.destination_ws.close()
        logger.info("Bot stopped")

    def authorize_account(self, ws, token):
        """Authorize an account with Deriv."""
        auth_request = {
            "authorize": token
        }
        ws.send(json.dumps(auth_request))

    def get_mt5_accounts(self, ws, is_source=True):
        """Get MT5 accounts for the authorized user."""
        request = {
            "mt5_login_list": 1
        }
        ws.send(json.dumps(request))
        logger.info(f"Requesting MT5 accounts for {'source' if is_source else 'destination'} token")

    def select_mt5_account(self, accounts, target_account_number=None, is_source=True):
        """
        Select an MT5 account based on specified criteria.
        
        Args:
            accounts (list): List of MT5 account dictionaries
            target_account_number (str, optional): Specific account number to match (with or without MT* prefix)
            is_source (bool): Whether this is for source account selection
        
        Returns:
            str: Selected account login or None if no suitable account found
        """
        account_type = "source" if is_source else "destination"
        
        if not accounts:
            logger.error(f"No MT5 accounts found for {account_type}")
            return None

        logger.info(f"Selecting {account_type} account. Target number: {target_account_number}")
        
        # First try: Look for exact account number match
        if target_account_number:
            target_number = str(target_account_number)
            for account in accounts:
                account_login = str(account.get("login", ""))
                
                # Try matching with and without the MT* prefix
                if (account_login == target_number or
                    account_login == f"MTD{target_number}" or
                    account_login == f"MTR{target_number}" or
                    account_login.endswith(target_number)):
                    
                    logger.info(f"Found exact matching {account_type} MT5 account: {account_login} "
                            f"(Type: {account.get('account_type')}, Group: {account.get('group')})")
                    return account_login
                    
            logger.error(f"Specified {account_type} account {target_number} not found in available accounts: "
                        f"{[acc.get('login') for acc in accounts]}")
            return None
        
        # Second try: Look for any enabled account with appropriate type
        for account in accounts:
            # Check if account is enabled and not trade disabled
            rights = account.get("rights", {})
            if rights.get("enabled", False) and not rights.get("trade_disabled", True):
                account_login = str(account.get("login"))
                logger.info(f"Selected {account_type} MT5 account: {account_login} "
                        f"(Type: {account.get('account_type')}, "
                        f"Group: {account.get('group')})")
                return account_login
        
        logger.error(f"No suitable {account_type} MT5 account found!")
        return None

    def subscribe_to_mt5_trades(self, ws):
        print("\n\nFetching trades from source account.")
        print(self.source_account_number)
        """Subscribe to MT5 positions and orders."""
        if not self.source_account_number:
            logger.error("MT5 account details not available")
            return

        # Subscribe to MT5 positions with more detailed parameters
        
        positions_request = {
            "transaction": 1,
            "subscribe": 1,
            "loginid": self.source_account_number,
            # "passthrough": ws_url,
            # "account_type": "demo",
            # "account_type": "real"  # Add this to ensure we're getting real account data
        }

        ws.send(json.dumps(positions_request))
        print("\n\nDumping Positions")
        print(json.dumps(positions_request))
        logger.info(f"Subscribed to MT5 positions for account {self.source_account_number}")

        # Subscribe to MT5 orders with more detailed parameters
        orders_request = {
            "transaction": 1,
            "subscribe": 1,
            "loginid": self.source_account_number,
            # "passthrough": ws_url,
            # "account_type": "demo",
            # "account_type": "real"  # Add this to ensure we're getting real account data
        }
        ws.send(json.dumps(orders_request))
        print("\n\nDumping orders")
        print(json.dumps(orders_request))
        logger.info(f"Subscribed to MT5 orders for account {self.source_account_number}")

    def on_source_message(self, ws, message):
        print(f'\n\Source received a message {message}')
        """Handle messages from source account."""
        try:
            data = json.loads(message)
            logger.debug(f"Source message received: {data}")

            if "authorize" in data and data["authorize"]:
                logger.info("Source account authorized successfully")
                self.get_mt5_accounts(ws, is_source=True)
            elif "mt5_login_list" in data:
                accounts = data.get("mt5_login_list", [])
                logger.info(f"Source MT5 accounts found: {accounts}")
                self.source_account_number = self.select_mt5_account(
                    accounts,
                    self.source_account_number,
                    is_source=True
                )
                if self.source_account_number:
                    self.subscribe_to_mt5_trades(ws)
                else:
                    logger.error("Failed to select source MT5 account")
            
            # New transaction handling block
            elif data.get('transaction'):
                print("\n\nTransactions came in")
                transaction = data.get('transaction', {})
                trade_type = transaction.get('action')
                print(transaction)


                if trade_type in ['buy', 'sell', 'create', 'update', 'delete']:
                    # Handle different trade scenarios
                    if transaction.get('contract_type') == 'position':
                        self.replicate_mt5_trade(transaction)
                    elif transaction.get('contract_type') == 'order':
                        self.replicate_mt5_order(transaction)
            
            # Keep existing position and order handling as fallback
            elif "mt5_get_positions" in data:
                print("Trying to get MT5 positions")
                positions = data.get("mt5_get_positions", [])
                if positions:
                    logger.info(f"Got MT5 positions")
                    logger.info(f"MT5 positions update: {positions}")
                    for position in positions:
                        self.replicate_mt5_trade(position)
            elif "mt5_get_orders" in data:
                orders = data.get("mt5_get_orders", [])
                if orders:
                    logger.info(f"MT5 orders update: {orders}")
                    for order in orders:
                        self.replicate_mt5_order(order)

        except json.JSONDecodeError:
            logger.error("Failed to parse source message")
        except Exception as e:
            logger.error(f"Error processing source message: {str(e)}")


    def on_destination_message(self, ws, message):
        print(f'\n\nDestinantion received a message {message}')
        """Handle messages from destination account."""
        try:
            data = json.loads(message)
            logger.debug(f"Destination message received: {data}")

            if "authorize" in data and data["authorize"]:
                logger.info("Destination account authorized successfully")
                self.get_mt5_accounts(ws, is_source=False)
            elif "mt5_login_list" in data:
                accounts = data.get("mt5_login_list", [])
                logger.info(f"Destination MT5 accounts found: {accounts}")
                
                self.destination_account_number = self.select_mt5_account(
                    accounts,
                    self.destination_account_number,
                    is_source=False
                )
                
                if not self.destination_account_number:
                    logger.error("Failed to select destination MT5 account")

            elif "mt5_new_order" in data:
                if data.get("error"):
                    logger.error(f"Trade replication failed: {data['error']['message']}")
                else:
                    logger.info(f"Trade replicated successfully: {data}")

        except json.JSONDecodeError:
            logger.error("Failed to parse destination message")
        except Exception as e:
            logger.error(f"Error processing destination message: {str(e)}")

    def replicate_mt5_trade(self, position):
        """Replicate an MT5 position on the destination account."""
        if not self.destination_ws:
            logger.error("Destination connection not available")
            return

        if not self.destination_account_number:
            logger.error("Destination MT5 account not set")
            return

        try:
            # Log the incoming position data
            logger.info(f"Attempting to replicate position: {json.dumps(position, indent=2)}")

            # Create MT5 trade request with all necessary parameters
            trade_request = {
                "mt5_new_order": 1,
                "login": self.destination_account_number,
                "symbol": position["symbol"],
                "type": position["type"],
                "volume": position["volume"],
                "price": position["price"],
                "action": position.get("action", "buy"),  # Add action type
                "time_in_force": "GTC",  # Good Till Cancelled
                "requestID": str(int(time.time()))  # Add unique request ID
            }
            
            # Log the outgoing request
            logger.info(f"Sending trade request: {json.dumps(trade_request, indent=2)}")
            
            self.destination_ws.send(json.dumps(trade_request))
            logger.info(f"Trade request sent for {position['symbol']}")

        except Exception as e:
            logger.error(f"Failed to replicate MT5 trade: {str(e)}")
            logger.error(f"Position data: {position}")

    def replicate_mt5_order(self, order):
        """Replicate an MT5 pending order on the destination account."""
        if not self.destination_ws:
            logger.error("Destination connection not available")
            return

        if not self.destination_account_number:
            logger.error("Destination MT5 account not set")
            return

        try:
            # Create MT5 order request
            order_request = {
                "mt5_new_order": 1,
                "login": self.destination_account_number,
                "symbol": order["symbol"],
                "type": order["type"],
                "volume": order["volume"],
                "price": order.get("price_open", order.get("price")),
                "sl": order.get("sl", 0),
                "tp": order.get("tp", 0)
            }
            
            # Log the outgoing request
            logger.info(f"Sending order request: {json.dumps(order_request, indent=2)}")
            
            self.destination_ws.send(json.dumps(order_request))
            logger.info(f"Order request sent for {order['symbol']}")

        except Exception as e:
            logger.error(f"Failed to replicate MT5 order: {str(e)}")
            logger.error(f"Order data: {order}")

def main():
    """Initialize and start the copy trading bot."""
    bot = DerivMT5CopyTradingBot(
        source_token = ``os.getenv("SOURCE_TOKEN")``,
        destination_token = os.getenv("DESTINATION_TOKEN1"),
        source_account_number = os.getenv("SOURCE_ACCOUNT_NUMBER"),
        destination_account_number = os.getenv("DESTINATION_ACCOUNT_NUMBER1"),
        app_id = os.getenv("DERIV_APP_ID"),
        
        
    )

    try:
        bot.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down the bot...")
        bot.stop()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        bot.stop()

if __name__ == "__main__":
    main()