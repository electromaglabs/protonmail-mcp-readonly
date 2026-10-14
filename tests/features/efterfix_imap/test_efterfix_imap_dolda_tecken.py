"""BDD: avslutande radbrytning och Unicode-siffror i UID och mappnamn avvisas (S6)."""
from pytest_bdd import scenarios

scenarios("efterfix_imap_dolda_tecken.feature")
