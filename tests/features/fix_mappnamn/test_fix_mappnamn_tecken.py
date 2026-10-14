"""BDD: mappnamn med %, * och .. ska gå att använda, men inte kontrolltecken."""
from pytest_bdd import scenarios

scenarios("fix_mappnamn_tecken.feature")
