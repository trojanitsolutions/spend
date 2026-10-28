# Copyright (c) 2026, Trojan IT Solutions and Contributors
# See license.txt

import frappe
import frappe.share

from spend.spend.activity import add_comment, get_activity, get_mentionable_users, remove_attachment
from spend.spend.notifications import get_notifications
from spend.tests.utils import SpendTestCase, make_supplier, make_user

MANAGER = "_spend_activity_manager@example.com"
GM = "_spend_activity_gm@example.com"
MANAGER_2 = "_spend_activity_manager2@example.com"


def attach(doc, file_name="note.txt"):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"content": "hello",
			"attached_to_doctype": doc.doctype,
			"attached_to_name": doc.name,
			"is_private": 1,
		}
	).insert(ignore_permissions=True)


class TestActivity(SpendTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		make_user(MANAGER, ["Accounts Manager"])
		make_user(GM, ["General Manager"])
		make_user(MANAGER_2, ["Accounts Manager"])

	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.set_user, "Administrator")
		self.supplier = make_supplier("_Test Activity Supplier")
		self.other = make_supplier("_Test Activity Other")

	def test_timeline_has_changes_comments_and_attachments(self):
		frappe.set_user(MANAGER)
		self.supplier.reload()
		self.supplier.tax_id = "29ABCDE1234F1Z5"
		self.supplier.save(ignore_version=False)  # tests skip versions by default
		add_comment("Supplier", self.supplier.name, "Check the GST number")
		file = attach(self.supplier)

		activity = get_activity("Supplier", self.supplier.name)
		self.assertEqual([f.name for f in activity["attachments"]], [file.name])
		self.assertTrue(activity["attachments"][0].can_remove)

		by_type = {}
		for e in activity["timeline"]:
			by_type.setdefault(e["type"], []).append(e["text"])
		self.assertIn("Created", by_type)
		self.assertTrue(any("29ABCDE1234F1Z5" in t for t in by_type["Version"]))
		self.assertIn("Check the GST number", by_type["Comment"])

	def test_user_without_read_cannot_see_activity(self):
		frappe.set_user(GM)
		with self.assertRaises(frappe.PermissionError):
			get_activity("Supplier", self.supplier.name)
		with self.assertRaises(frappe.PermissionError):
			add_comment("Supplier", self.supplier.name, "hi")

	def test_comment_is_escaped_and_not_empty(self):
		frappe.set_user(MANAGER)
		add_comment("Supplier", self.supplier.name, "<b>bold</b>")
		content = frappe.db.get_value(
			"Comment", {"reference_doctype": "Supplier", "reference_name": self.supplier.name, "comment_type": "Comment"}, "content"
		)
		self.assertEqual(content, "&lt;b&gt;bold&lt;/b&gt;")
		comments = [e["text"] for e in get_activity("Supplier", self.supplier.name)["timeline"] if e["type"] == "Comment"]
		self.assertEqual(comments, ["<b>bold</b>"])
		with self.assertRaises(frappe.ValidationError):
			add_comment("Supplier", self.supplier.name, "   ")

	def test_remove_attachment(self):
		file = attach(self.supplier)
		other_file = attach(self.other)
		frappe.share.add("Supplier", self.supplier.name, GM, read=1, write=0)

		frappe.set_user(GM)
		self.assertFalse(get_activity("Supplier", self.supplier.name)["attachments"][0].can_remove)
		with self.assertRaises(frappe.PermissionError):
			remove_attachment("Supplier", self.supplier.name, file.name)

		frappe.set_user(MANAGER)
		with self.assertRaises(frappe.ValidationError):
			remove_attachment("Supplier", self.supplier.name, other_file.name)
		remove_attachment("Supplier", self.supplier.name, file.name)
		self.assertFalse(frappe.db.exists("File", file.name))

	def test_uploader_can_remove_own_file(self):
		frappe.share.add("Supplier", self.supplier.name, GM, read=1, write=0)
		frappe.set_user(GM)
		file = attach(self.supplier)
		remove_attachment("Supplier", self.supplier.name, file.name)
		self.assertFalse(frappe.db.exists("File", file.name))

	def last_comment(self):
		return frappe.get_last_doc(
			"Comment", filters={"reference_doctype": "Supplier", "reference_name": self.supplier.name, "comment_type": "Comment"}
		)

	def test_mentionable_users_can_read_the_document(self):
		frappe.set_user(MANAGER)
		users = {u.user for u in get_mentionable_users("Supplier", self.supplier.name)}
		self.assertIn(MANAGER_2, users)
		self.assertNotIn(GM, users)
		self.assertNotIn(MANAGER, users)

	def test_tagged_user_is_notified(self):
		frappe.set_user(MANAGER)
		name = frappe.utils.get_fullname(MANAGER_2)
		add_comment("Supplier", self.supplier.name, f"@{name} please check <b>this</b>", [MANAGER_2, GM])

		content = self.last_comment().content
		self.assertIn(f'data-id="{MANAGER_2}"', content)
		self.assertNotIn(GM, content)
		self.assertIn("&lt;b&gt;", content)

		comments = [e for e in get_activity("Supplier", self.supplier.name)["timeline"] if e["type"] == "Comment"]
		self.assertEqual(comments[0]["text"], f"@{name} please check <b>this</b>")
		self.assertEqual(comments[0]["mentions"], [{"user": MANAGER_2, "full_name": name}])

		frappe.set_user(MANAGER_2)
		mention = [n for n in get_notifications() if n.type == "Mention" and n.document_name == self.supplier.name]
		self.assertEqual(len(mention), 1)
		self.assertEqual(mention[0].link, f"/spend/suppliers/{self.supplier.name}")

	def test_untagged_name_is_plain_text(self):
		frappe.set_user(MANAGER)
		name = frappe.utils.get_fullname(MANAGER_2)
		add_comment("Supplier", self.supplier.name, f"@{name} hello")
		self.assertNotIn("mention", self.last_comment().content)
