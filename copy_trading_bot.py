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
    def __init__(self, source_token, destination_token, source_account_number=None, 
                 destination_account_number=None, app_id="1089"):
        self.source_token = source_token
        self.destination_token = destination_token
        self.source_account_number = source_account_number
        self.destination_account_number = destination_account_number
        self.ws_url = f"wss://ws.binaryws.com/websockets/v3?app_id={app_id}"
        self.source_ws = None
        self.destination_ws = None
        self.source_mt5_account = None
        self.destination_mt5_account = None
        self.should_run = Event()
        self.should_run.set()
        self.ping_interval = 15
        self.reconnect_delay = 5
        self.connection_retries = 3
        self.retry_delay = 5

    def start(self):
        """Start both source and destination WebSocket connections."""
        try:
            self.start_source_connection()
            self.start_destination_connection()
            Thread(target=self.keep_alive_ping, args=(self.source_ws, "source")).start()
            Thread(target=self.keep_alive_ping, args=(self.destination_ws, "destination")).start()
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
                if (account_login == target_number or                  # Exact match
                    account_login == f"MTD{target_number}" or         # Demo account prefix
                    account_login == f"MTR{target_number}" or         # Real account prefix
                    account_login.endswith(target_number)):           # Match end of number
                    
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

    

    def _run_websocket(self, ws, name):
        """Run WebSocket connection with automatic reconnection."""
        retries = 0
        while self.should_run.is_set():
            try:
                ws.run_forever(ping_interval=30, ping_timeout=10)
                if self.should_run.is_set():
                    retries += 1
                    if retries <= self.connection_retries:
                        logger.info(f"Attempting to reconnect {name} WebSocket (attempt {retries}/{self.connection_retries})...")
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"Max retries reached for {name} WebSocket. Stopping bot.")
                        self.stop()
                        break
            except Exception as e:
                logger.error(f"Error in {name} WebSocket connection: {str(e)}")
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

    def subscribe_to_mt5_trades(self, ws):
        """Subscribe to MT5 positions and orders."""
        if not self.source_mt5_account:
            logger.error("MT5 account details not available")
            return

        # Subscribe to MT5 positions
        positions_request = {
            "mt5_get_positions": 1,
            "login": self.source_mt5_account,
            "subscribe": 1
        }
        ws.send(json.dumps(positions_request))
        logger.info("Subscribed to MT5 positions")

        # Subscribe to MT5 orders
        orders_request = {
            "mt5_get_orders": 1,
            "login": self.source_mt5_account,
            "subscribe": 1
        }
        ws.send(json.dumps(orders_request))
        logger.info("Subscribed to MT5 orders")

    def on_source_message(self, ws, message):
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
                
                self.source_mt5_account = self.select_mt5_account(
                    accounts,
                    self.source_account_number,
                    is_source=True
                )
                
                if self.source_mt5_account:
                    self.subscribe_to_mt5_trades(ws)
                else:
                    logger.error("Failed to select source MT5 account")

            elif "mt5_get_positions" in data:
                positions = data.get("mt5_get_positions", [])
                if positions:
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
                
                self.destination_mt5_account = self.select_mt5_account(
                    accounts,
                    self.destination_account_number,
                    is_source=False
                )
                
                if not self.destination_mt5_account:
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

        try:
            # Create MT5 trade request
            trade_request = {
                "mt5_new_order": 1,
                "login": self.destination_mt5_account,
                "symbol": position["symbol"],
                "type": position["type"],
                "volume": position["volume"],
                "price": position["price"]
            }
            
            self.destination_ws.send(json.dumps(trade_request))
            logger.info(f"Replicating MT5 trade: {position['symbol']}")

        except Exception as e:
            logger.error(f"Failed to replicate MT5 trade: {str(e)}")

    def replicate_mt5_order(self, order):
        """Replicate an MT5 pending order on the destination account."""
        if not self.destination_ws:
            logger.error("Destination connection not available")
            return

        try:
            # Create MT5 order request
            order_request = {
                "mt5_new_order": 1,
                "login": self.destination_mt5_account,
                "symbol": order["symbol"],
                "type": order["type"],
                "volume": order["volume"],
                "price": order.get("price_open", order.get("price")),
                "sl": order.get("sl", 0),
                "tp": order.get("tp", 0)
            }
            
            self.destination_ws.send(json.dumps(order_request))
            logger.info(f"Replicating MT5 order: {order['symbol']}")

        except Exception as e:
            logger.error(f"Failed to replicate MT5 order: {str(e)}")

def main():
    # Initialize and start the copy trading bot
    bot = DerivMT5CopyTradingBot(
        source_token="D4mOMe2m0UB5h2o",
        destination_token="W9LpYCwJNwuFKqY",
        source_account_number="31782142",  # Replace with your source MT5 account number
        destination_account_number="5677747"  # Replace with your destination MT5 account number
    )
    
    try:
        bot.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down copy trading bot...")
        bot.stop()
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        bot.stop()

if __name__ == "__main__":
    main()