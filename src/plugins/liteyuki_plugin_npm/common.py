from src.utils.data import Database, LiteModel
from src.utils.data_manager import plugin_db

LNPM_COMMAND_START = "lnpm"




class InstalledPlugin(LiteModel):
    module_name: str


plugin_db.auto_migrate(InstalledPlugin)
