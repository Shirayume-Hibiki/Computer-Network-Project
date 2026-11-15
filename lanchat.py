'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys

# Delegate directly to script/deploy/lanchat.py
DEPLOY_LANCHAT = os.path.join(os.path.dirname(__file__), "script", "deploy", "lanchat.py")
if __name__ == "__main__":
    with open(DEPLOY_LANCHAT, "r", encoding="utf-8") as f:
        code = compile(f.read(), DEPLOY_LANCHAT, "exec")
        exec(code, {"__name__": "__main__", "__file__": DEPLOY_LANCHAT})
