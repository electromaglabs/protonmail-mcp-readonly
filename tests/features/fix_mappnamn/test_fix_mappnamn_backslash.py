"""BDD: etiketter med snedstreck (backslash) i namnet ska gå att nå."""
from pytest_bdd import scenarios

scenarios("fix_mappnamn_backslash.feature")
