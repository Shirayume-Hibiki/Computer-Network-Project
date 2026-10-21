# Credential Addon Guide

Every source code file created in this project (excluding `__init__.py` and `.toml` configuration files) must include a credential header at the very top of the file to document authorship and track major revisions.

---

## Header Template

Copy and paste the following docstring block at the top of your `.py` files (before any `import` statements):

```python
'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  <Your_Name>               ║
║  Creation date:            dd/mm/yy                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''
```

### Example:

```python
'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            18/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''
```

---

## Formatting Rules

* **Date Format:** Always use `dd/mm/yy` (e.g., `18/10/26`, `21/10/26`).
* **Exemptions:** Do **not** add this block to `__init__.py` files or `.toml` configuration files (as it will either clutter empty package markers or break TOML syntax).
* **Edits:** When another contributor modifies an existing file, append the edit date and contributor name under `Edit dates / contributor:`.

---

[Back to README](./README.md)
