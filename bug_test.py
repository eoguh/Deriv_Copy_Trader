import os
import asyncio
from deriv_api import DerivAPI


# Replace with your actual API endpoint and app ID
async def create_api_instance():
    try:
        return DerivAPI(endpoint="wss://ws.binary.com/websockets/v3", app_id=os.getenv("DERIV_APP_ID"))
    except Exception as e:
        print(f"Error creating DerivAPI instance: {e}")
        return None  # Handle error or return None if creation fails

async def main():
    # Create the DerivAPI instance within the async function
    api = await create_api_instance()
    if not api:
        return  # Exit if API creation failed

    # Subscribe to the trade feed
    await api.subscribe_to_trade("R_50")  # Replace "R_50" with the desired symbol

    # Handle incoming trade updates
    async for msg in api.listen():
        if msg["msg-type"] == "trade":
            # Process the trade data
            print(msg)


# Run the event loop only once (moved outside the main guard)
async def run_event_loop():
    loop = asyncio.get_event_loop()  # Get or create an event loop
    try:
        await loop.run_until_complete(main())  # Run the main coroutine
    except Exception as e:
        print(f"Error running event loop: {e}")

# Call asyncio.run only once at the very end
if __name__ == "__main__":
    asyncio.run(run_event_loop())  # Run the event loop function once