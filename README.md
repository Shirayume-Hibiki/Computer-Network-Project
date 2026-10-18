# Computer Network Project

This repository contains the core codebase for the Computer Network Project. Please follow the structured guidelines below to maintain clean, readable, and highly maintainable code.

---

##  Code Style Guide

###  Import Structure
To avoid dependency mess, structure all module imports strictly in the following order:

1. **Standard Library Imports:** Native Python standard modules (e.g., `sys`, `os`, `socket`).
   *(Blank Line)*
2. **Third-Party Libraries:** External packages installed via package managers (e.g., `scapy`, `requests`).
   *(Blank Line)*
3. **Internal Libraries:** Custom local modules created specifically for this project.

*Example:*
```python
import os
import socket

import scapy.all as scapy

from internal_libs.packet_parser import Header
```

---

###  Naming Conventions

We implement a specific naming scheme to keep our hybrid codebase clean. Please adhere to the following cases:

*   **Functions:** `camelCase` &nbsp;➔&nbsp; `parsePacket()`, `sendData()`
*   **Classes:** `PascalCase` &nbsp;➔&nbsp; `NetworkServer`, `ClientConnection`
*   **Variables:** `lowercase` &nbsp;➔&nbsp; `payload`, `buffer`
*   **Constants:** `SCREAMING_SNAKE_CASE` &nbsp;➔&nbsp; `MAX_BUFFER_SIZE`, `PORT_NUMBER`

> 💡 *Note: Additional specific naming rules will be updated as the project scales.*

---

## ❓ Frequently Asked Questions (FAQ)

#### Q: Where should I put external libraries?
**A:** Place all source codes or standalone files of external dependencies inside the designated directory:
`./external_libs/`

#### Q: What code should we commit?
**A:** For the time being, **focus completely on finishing and testing internal libraries**. Keeping them self-contained and modular now will ensure an easy assembly and integration phase later in the development cycle.
