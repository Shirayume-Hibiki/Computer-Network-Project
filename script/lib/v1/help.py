'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Gemini 3.8 Flash          ║
║  Creation date:            05/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from common_functions import showHelp, help

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    showHelp(target)
