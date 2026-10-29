import frappe
from frappe.utils import nowdate


def validate(doc, method=None):
	"""EOBI Deduction Start Date: filled with today when EOBI Applicable is ticked on
	(unless a date was entered), cleared when it is ticked off. Employees that already
	had it ticked keep whatever date was entered manually."""
	if not doc.get("custom_eobi_applicable"):
		doc.custom_eobi_deduction_start_date = None
	elif not doc.get("custom_eobi_deduction_start_date") and doc.has_value_changed("custom_eobi_applicable"):
		doc.custom_eobi_deduction_start_date = nowdate()
