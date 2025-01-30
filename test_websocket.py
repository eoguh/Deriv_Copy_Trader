import websocket
import threading
import os


class WebSocketTest:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.ws = None

    def on_message(self, ws, message):
        print(f"Message received: {message}")

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print(f"WebSocket closed: {close_msg} (Code: {close_status_code})")

    def on_open(self, ws):
        print("WebSocket connection opened!")
        # Example: Send a ping request to test the connection
        ws.send('{"ping": 1}')
        print("Ping sent to server.")

    def start(self):
        print(f'\n\n\n\n\nHello')
        # print(f'\n\n\n\n\n{os.environ}')
        print(f'\n\n\n\n\n{os.getenv("SOURCE_TOKEN")}')
        
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        # Run the WebSocket in a separate thread
        thread = threading.Thread(target=self.ws.run_forever)
        thread.daemon = True
        thread.start()


if __name__ == "__main__":
    test_url = "wss://ws.binaryws.com/websockets/v3?app_id=1089"
    ws_tester = WebSocketTest(test_url)
    ws_tester.start()

    # Allow time to test the connection
    import time
    time.sleep(10)  # Adjust as needed
