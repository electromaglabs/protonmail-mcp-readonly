"""BDD: delete_folder vägrar ta bort en mapp med undermappar utan force (S3)."""
from pytest_bdd import scenarios

scenarios("efterfix_imap_undermappar.feature")
