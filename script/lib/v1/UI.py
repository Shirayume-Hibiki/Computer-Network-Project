'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            18/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import datetime
    
SERVER_COLOR = '\033[94m' # Blue
CLIENT_COLOR = '\033[92m' # Green
SYSTEM_COLOR = '\033[90m' # Gray
WARN_COLOR   = '\033[93m' # Yellow
ERROR_COLOR  = '\033[91m' # Red
RESET = '\033[0m'
BOLD = '\033[1m'
# TODO: Set these params to ./configs/UI_config.toml

class UI:
    # Method to get current time
    @staticmethod
    def getTime():
        return datetime.datetime.now().strftime("%H:%M:%S")

    @classmethod
    def _formatAndPrint(cls, color: str, role: str, action: str, msg: str):
        timestr = f"[{cls.getTime()}]"
        pfx = f"{color}{BOLD}-> [{role}] ({action}):{RESET}"
        print(f"{timestr:<10} {pfx} {msg}")
    
    @classmethod
    def serverMsg(cls, msg: str, action: str = "RESPONSE"):
        cls._formatAndPrint(SERVER_COLOR, "SERVER", action, msg)

    @classmethod
    def clientMsg(cls, msg: str, action: str = "REQUEST"):
        cls._formatAndPrint(CLIENT_COLOR, "CLIENT", action, msg)

    @classmethod
    def systemMsg(cls, msg: str, action: str = "INFO"):
        cls._formatAndPrint(SYSTEM_COLOR, "SYSTEM", action, msg)

    @classmethod
    def warningMsg(cls, msg: str, action: str = "WARNING"):
        cls._formatAndPrint(WARN_COLOR, "WARNING", action, msg)

    @classmethod
    def errorMsg(cls, msg: str, action: str = "ERROR"):
        cls._formatAndPrint(ERROR_COLOR, "ERROR", action, msg)