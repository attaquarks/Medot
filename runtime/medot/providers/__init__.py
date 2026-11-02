"""AI providers: BYOK model discovery + model profiles.

Discovery fetches the live model list from the provider so the user picks
from real models instead of typing ids (they can still type one). Keys live
only in the OS keystore; `model_profiles` rows store a credential_ref, never
a key.
"""
