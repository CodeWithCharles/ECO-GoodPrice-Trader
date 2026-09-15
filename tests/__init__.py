"""Suite de tests : python -m unittest discover -s tests -t . depuis src/.

Les tests n'appellent jamais le reseau : ils construisent des payloads
a la main (fixtures.py) ou passent par OfflineClient.
"""
