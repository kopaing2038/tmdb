from swibots import Client
import config

app = Client(
     name=SESSION,
     api_id=config.API_ID,
     api_hash=config.API_HASH,
     bot_token=config.BOT_TOKEN,
     workers=50,
     plugins={"root": "plugins"},
     )
