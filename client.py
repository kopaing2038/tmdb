from swibots import Client
import config

app = Client(
     name=config.SESSION,
     api_id=config.API_ID,
     api_hash=config.API_HASH,
     token=config.BOT_TOKEN,  # Make sure to include the token argument
     workers=50,
     plugins={"root": "plugins"},
)
