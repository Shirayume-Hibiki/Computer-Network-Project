'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            18/10/26                  ║
║  Edit dates / contributor:                           ║
║  03/11/26 diamboy                                    ║
║  13/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import datetime
import os
import threading
import tomllib

from UI import UI

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
LOG_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "log_config.toml")
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
FILE_TIME_FORMAT = "%d-%m-%Y_%H-%M-%S"
TIME_FORMAT = "%d/%m/%Y ~ %H:%M:%S"

def loadLogConfig(configpath: str = LOG_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        with open(configpath, "rb") as cfgfile:
            data = tomllib.load(cfgfile)
            return data.get("logging", data)
    return {}

class CNLogger:
    _lock = threading.Lock()

    def __init__(self, instancepfx: str = "session", configpath: str = LOG_CONFIG_PATH):
        # Sanitize instancepfx to prevent invalid characters or path traversal
        clean_pfx = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in instancepfx).strip("_")
        self.instancepfx = clean_pfx or "session"
        self.configpath: str = configpath
        self.logdir: str = LOG_DIR
        self.filetimeformat: str = FILE_TIME_FORMAT
        self.timeformat: str = TIME_FORMAT
        self.filepath: str = ""
        self._file_handle = None

    def initLogger(self) -> str:
        with self._lock:
            if self.filepath and self._file_handle:
                return self.filepath
            config = loadLogConfig(self.configpath)
            rawlogdir = config.get("log_dir", LOG_DIR)
            self.logdir = rawlogdir if os.path.isabs(rawlogdir) else os.path.join(PROJECT_ROOT, rawlogdir)
            self.timeformat = config.get("time_format", TIME_FORMAT)

            os.makedirs(self.logdir, exist_ok=True)
            inittime = datetime.datetime.now().strftime(self.filetimeformat)
            filename = f"{self.instancepfx}_{inittime}.log"
            self.filepath = os.path.join(self.logdir, filename)
            self._file_handle = open(self.filepath, "a", encoding="utf-8", buffering=1)
            return self.filepath

    def getTimestamp(self) -> str:
        return datetime.datetime.now().strftime(self.timeformat)

    def writeLog(self, role: str, action: str, msg: str):
        with self._lock:
            if not self._file_handle:
                self.initLogger()
            timestamp = f"[{self.getTimestamp()}]"
            logline = f"{timestamp} -> [{role}] ({action}): {msg}\n"
            self._file_handle.write(logline)
            self._file_handle.flush()

    def close(self):
        with self._lock:
            if self._file_handle:
                try:
                    self._file_handle.close()
                except Exception:
                    pass
                self._file_handle = None

    def logServer(self, msg: str, action: str = "INFO", console: bool = False):
        self.writeLog("SERVER", action, msg)
        if console:
            UI.serverMsg(msg, action)

    def logClient(self, msg: str, action: str = "INFO", console: bool = False):
        self.writeLog("CLIENT", action, msg)
        if console:
            UI.clientMsg(msg, action)

    def logSystem(self, msg: str, action: str = "INFO", console: bool = False):
        self.writeLog("SYSTEM", action, msg)
        if console:
            UI.systemMsg(msg, action)

    def logWarn(self, msg: str, action: str = "WARN", console: bool = True):
        self.writeLog("WARN", action, msg)
        if console:
            UI.warningMsg(msg, action)

    def logError(self, msg: str, action: str = "ERROR", console: bool = True):
        self.writeLog("ERROR", action, msg)
        if console:
            UI.errorMsg(msg, action)
