import os
import asyncio
from deriv_api import DerivAPI
import logging


class DerivCopyTrader:
    def __init__(self, source_config, destination_configs):
        """
        Initialize the copy trading bot.
        :param source_config: Dictionary with source account details
        :param destination_configs: List of destination account configurations
        """
        self.source_token = source_config['token']
        self.source_account_number = source_config.get('account_number')
        self.destination_configs = destination_configs
        self.source_client = None
        self.destination_clients = {}
        self.active_trades = {}

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    async def connect(self):
        """Connect to the Deriv API for source and destination accounts."""
        try:
            # Connect to the source account
            self.source_client = DerivAPI(token=self.source_token, app_id=os.getenv("DERIV_APP_ID"))
            self.logger.info("Connected to source account.")

            # Connect to all destination accounts
            for config in self.destination_configs:
                client = DerivAPI(token=config['token'], app_id=os.getenv("DERIV_APP_ID"))
                self.destination_clients[config['token']] = {'client': client}
            self.logger.info("Connected to all destination accounts.")
        except Exception as e:
            self.logger.error(f"Error during connection: {e}")
            raise

    async def copy_trade(self, trade_details):
        """
        Copy trade to destination accounts.
        :param trade_details: Original trade details from the source account
        """
        if self.source_account_number and trade_details.get('account_number') != self.source_account_number:
            return  # Skip if the trade doesn't match the source account

        for dest_config in self.destination_configs:
            dest_token = dest_config['token']
            dest_client = self.destination_clients[dest_token]['client']

            try:
                await self._execute_trade_copy(dest_client, trade_details)
            except Exception as e:
                self.logger.error(f"Error copying trade to {dest_token}: {e}")

    async def _execute_trade_copy(self, dest_client, trade_details):
        """
        Execute the trade copy for a specific destination account.
        :param dest_client: Destination Deriv API client
        :param trade_details: Source trade details
        """
        try:
            scaled_lot_size = await self.calculate_scaled_lot_size(trade_details, dest_client)
            trade_params = {
                'symbol': trade_details['symbol'],
                'contract_type': trade_details['contract_type'],
                'lot_size': scaled_lot_size,
                'stop_loss': trade_details.get('stop_loss'),
                'take_profit': trade_details.get('take_profit'),
            }
            copied_trade = await dest_client.create_trade(**trade_params)
            self.active_trades[copied_trade['id']] = {
                'source_trade_id': trade_details['id'],
                'destination_token': dest_client.token
            }
            self.logger.info(f"Trade copied successfully: {copied_trade}")
        except Exception as e:
            self.logger.error(f"Error executing trade copy: {e}")

    async def calculate_scaled_lot_size(self, source_trade, dest_client):
        """Calculate the scaled lot size based on account balances."""
        try:
            source_balance = await self.source_client.get_account_balance()
            dest_balance = await dest_client.get_account_balance()
            scaling_factor = dest_balance / source_balance
            return source_trade['lot_size'] * scaling_factor
        except Exception as e:
            self.logger.error(f"Error calculating scaled lot size: {e}")
            return source_trade['lot_size']

    async def update_trade_parameters(self, trade_update):
        """
        Update parameters (e.g., stop loss, take profit) for copied trades.
        :param trade_update: Updated trade details
        """
        try:
            for trade_id, trade_info in self.active_trades.items():
                if trade_info['source_trade_id'] == trade_update['id']:
                    dest_token = trade_info['destination_token']
                    dest_client = self.destination_clients[dest_token]['client']
                    await dest_client.update_trade(trade_id, **trade_update)
                    self.logger.info(f"Trade updated: {trade_update}")
        except Exception as e:
            self.logger.error(f"Error updating trade parameters: {e}")

    async def start_copying(self):
        """Start listening for trades and copying them."""
        try:
            await self.source_client.listen_trades(
                on_trade_open=self.copy_trade,
                on_trade_update=self.update_trade_parameters
            )
        except Exception as e:
            self.logger.error(f"Error starting trade copying: {e}")


async def main():
    SOURCE_CONFIG = {
        'token': os.getenv("SOURCE_TOKEN"),
        'account_number': os.getenv("SOURCE_ACCOUNT_NUMBER")
    }
    DESTINATION_CONFIGS = [
        {'token': os.getenv("DESTINATION_TOKEN1")},
        {'token': os.getenv("DESTINATION_TOKEN2")}
    ]

    copy_trader = DerivCopyTrader(SOURCE_CONFIG, DESTINATION_CONFIGS)

    try:
        await copy_trader.connect()
        await copy_trader.start_copying()
    except Exception as e:
        print(f"Error in the copy trading bot: {e}")


if __name__ == "__main__":
    asyncio.run(main())
