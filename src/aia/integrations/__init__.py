"""External integrations, each behind a provider-agnostic interface so a user can
swap Gmail for Outlook, Baileys for Cloud API, USDA for Nutritionix, etc. without
touching agent code. Credentials are obtained via OAuth and stored encrypted.
"""
