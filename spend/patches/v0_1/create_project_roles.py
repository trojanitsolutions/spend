from spend.spend.setup import create_roles


def execute():
	"""Project Manager and Project User are named in DocPerms, so they exist before the doctypes sync."""
	create_roles()
