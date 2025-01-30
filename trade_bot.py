import os
import asyncio
from deriv_api import DerivAPI
import logging
from collections import defaultdict


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
APP_ID = os.getenv("DERIV_APP_ID")
USER_A_TOKEN = os.getenv("SOURCE_TOKEN")
USER_B_TOKEN = os.getenv("DESTINATION_TOKEN1")

# Track contract mappings between accounts
contract_mapping = defaultdict(dict)

async def replicate_trades():
    """Main function to replicate trades including sell transactions"""
    api_user_a = DerivAPI(app_id=APP_ID)
    api_user_b = DerivAPI(app_id=APP_ID)

    try:
        # Authenticate both users
        auth_a = await api_user_a.authorize(USER_A_TOKEN)
        auth_b = await api_user_b.authorize(USER_B_TOKEN)
        
        if 'error' in auth_a or 'error' in auth_b:
            logger.error("Authentication failed")
            return

        logger.info("Authentication successful")

        # Subscribe to User A's transaction stream
        await api_user_a.subscribe({'transaction': 1, 'subscribe': 1})
        logger.info("Listening for transactions...")

        while True:
            message = await api_user_a.listen()
            if message.get('msg_type') == 'transaction':
                transaction = message.get('transaction', {})
                action = transaction.get('action')
                
                if action == 'buy':
                    await process_buy_transaction(api_user_a, api_user_b, transaction)
                elif action == 'sell':
                    await process_sell_transaction(api_user_a, api_user_b, transaction)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        await shutdown(api_user_a, api_user_b)

async def process_buy_transaction(api_user_a, api_user_b, transaction):
    """Handle buy transactions and store contract mapping"""
    try:
        contract_id_a = transaction['contract_id']
        logger.info(f"New buy transaction detected: {contract_id_a}")

        # Get original contract details
        contract = await api_user_a.call({
            "proposal_open_contract": 1,
            "contract_id": contract_id_a
        })

        if 'error' in contract:
            logger.error(f"Error getting contract: {contract['error']['message']}")
            return

        contract_details = contract['proposal_open_contract']

        # Prepare buy parameters for User B
        buy_params = {
            "buy_contract": 1,
            "parameters": {
                "amount": contract_details['buy_price'],
                "currency": contract_details['currency'],
                "symbol": contract_details['symbol'],
                "contract_type": contract_details['contract_type'],
                "duration": contract_details['duration'],
                "duration_unit": contract_details['duration_unit'],
                "basis": "stake"
            }
        }

        # Add optional parameters
        for param in ['barrier', 'barrier2', 'limit_order']:
            if param in contract_details:
                buy_params['parameters'][param] = contract_details[param]

        # Execute on User B's account
        response = await api_user_b.call(buy_params)
        
        if 'error' in response:
            logger.error(f"Replication failed: {response['error']['message']}")
        else:
            contract_id_b = response['buy_contract']['contract_id']
            contract_mapping[contract_id_a] = contract_id_b
            logger.info(f"Trade replicated! A:{contract_id_a} → B:{contract_id_b}")

    except Exception as e:
        logger.error(f"Buy processing error: {str(e)}")

async def process_sell_transaction(api_user_a, api_user_b, transaction):
    """Handle sell transactions using contract mapping"""
    try:
        contract_id_a = transaction['contract_id']
        sell_price = transaction['amount']
        
        if contract_id_a not in contract_mapping:
            logger.error(f"No mapped contract for {contract_id_a}")
            return

        contract_id_b = contract_mapping[contract_id_a]
        logger.info(f"Processing sell: A:{contract_id_a} → B:{contract_id_b}")

        # Execute sell on User B's account
        response = await api_user_b.call({
            "sell_contract": 1,
            "contract_id": contract_id_b,
            "price": sell_price
        })

        if 'error' in response:
            logger.error(f"Sell failed: {response['error']['message']}")
        else:
            del contract_mapping[contract_id_a]
            logger.info(f"Sell successful! B:{contract_id_b}")

    except Exception as e:
        logger.error(f"Sell processing error: {str(e)}")

async def shutdown(*apis):
    """Cleanup connections"""
    for api in apis:
        await api.clear()
    logger.info("Shutdown complete")

if __name__ == "__main__":
    asyncio.run(replicate_trades())