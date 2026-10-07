frappe.ui.form.on("Employee", {
	refresh(frm) {
		render_salary_info(frm);
	},
	custom_eobi_applicable(frm) {
		if (!frm.doc.custom_eobi_applicable) {
			frm.set_value("custom_eobi_amount", 0);
		}
	},
});

function render_salary_info(frm) {
	const wrapper = frm.fields_dict.custom_salary_info_html;
	if (!wrapper) return;
	if (frm.is_new()) {
		wrapper.$wrapper.html(`<p class="text-muted">${__("Save the employee to see salary details.")}</p>`);
		return;
	}
	frappe.call({
		method: "overtime_in_salary.overtime_in_salary.employee_salary_info.get_employee_salary_info",
		args: { employee: frm.doc.name },
		callback(r) {
			wrapper.$wrapper.html(build_html(r.message || {}, frm.doc.salary_currency, frm.doc.custom_eobi_applicable ? frm.doc.custom_eobi_amount : 0));
		},
	});
}

function build_html(data, currency, eobi_amount) {
	const esc = frappe.utils.escape_html;
	const fmt = (v) => format_currency(v || 0, currency);
	const fdate = (d) => (d ? frappe.datetime.str_to_user(d) : "");
	const table = (head, rows) =>
		`<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead>
			<tbody>${rows.join("") || `<tr><td colspan="${head.length}" class="text-muted">${__("None")}</td></tr>`}</tbody>
		</table></div>`;
	let html = "";

	// 1 & 2: structure and components
	const s = data.structure;
	html += `<h6>${__("Salary Structure")}</h6>`;
	if (!s) {
		html += `<p class="text-muted">${__("No submitted Salary Structure Assignment is effective for this employee.")}</p>`;
	} else {
		html += `<p><b>${frappe.utils.get_form_link("Salary Structure", s.salary_structure, true)}</b>
			&middot; ${__("Assignment")} ${frappe.utils.get_form_link("Salary Structure Assignment", s.assignment, true)}
			&middot; ${__("From")} ${fdate(s.from_date)} &middot; ${__("Base")} ${fmt(s.base)}
			&middot; ${esc(s.payroll_frequency || "")}</p>`;
		html += table(
			[__("Type"), __("Component"), __("Abbr"), __("Amount / Formula"), __("Condition"), __("Depends on Payment Days")],
			s.components.map(
				(c) => `<tr><td>${c.type}</td><td>${esc(c.component)}</td><td>${esc(c.abbr || "")}</td>
					<td>${c.formula ? `<code>${esc(c.formula)}</code>` : fmt(c.amount)}</td>
					<td>${esc(c.condition || "")}</td><td>${c.depends_on_payment_days ? __("Yes") : __("No")}</td></tr>`
			)
		);
	}

	if (flt(eobi_amount)) {
		html += `<p><b>${__("EOBI Amount")}:</b> ${fmt(eobi_amount)}</p>`;
	}

	// 4: loans
	html += `<h4 class="mt-4 mb-3" style="font-weight:700;font-size:20px;color:var(--heading-color, var(--text-color));">${__("Loan History")}</h4>`;
	const loans = data.loans || {};
	if (!loans.available) {
		// Lending app not installed: nothing to show
	} else if (!loans.loans.length) {
		html += `<p class="text-muted">${__("No loans for this employee.")}</p>`;
	} else {
		const sum = (k) => loans.loans.reduce((a, l) => a + (l[k] || 0), 0);
		html += table(
			[__("Loan"), __("Type"), __("Status"), __("Disbursed"), __("Total Payable"), __("Deducted / Paid"), __("Remaining"), __("Monthly")],
			loans.loans
				.map(
					(l) => `<tr><td>${frappe.utils.get_form_link("Loan", l.name, true)}</td><td>${esc(l.loan_type || "")}</td>
					<td>${esc(l.status || "")}</td><td>${fmt(l.disbursed_amount || l.loan_amount)}</td>
					<td>${fmt(l.total_payable)}</td><td>${fmt(l.total_paid)}</td><td>${fmt(l.remaining)}</td>
					<td>${fmt(l.monthly_repayment_amount)}</td></tr>`
				)
				.concat(
					`<tr class="font-weight-bold"><td colspan="4">${__("Total")}</td><td>${fmt(sum("total_payable"))}</td>
					<td>${fmt(sum("total_paid"))}</td><td>${fmt(sum("remaining"))}</td><td></td></tr>`
				)
		);
		loans.loans.forEach((l) => {
			const rows = (l.repayments || []).map(
				(p) => `<tr><td>${fdate(p.posting_date)}</td><td>${frappe.utils.get_form_link("Loan Repayment", p.name, true)}</td>
				<td>${esc(p.repayment_type || "")}</td><td>${fmt(p.principal_amount_paid)}</td><td>${fmt(p.total_interest_paid)}</td><td>${fmt(p.amount_paid)}</td></tr>`
			);
			const ded = (l.salary_slip_deductions || []).map(
				(p) => `<tr><td>${fdate(p.start_date)} – ${fdate(p.end_date)}</td><td>${frappe.utils.get_form_link("Salary Slip", p.salary_slip, true)}</td>
				<td>${fmt(p.principal_amount)}</td><td>${fmt(p.interest_amount)}</td><td>${fmt(p.total_payment)}</td></tr>`
			);
			html += `<p class="mt-3 mb-1"><b>${esc(l.name)}</b> – ${__("Repayments")}</p>` +
				table([__("Date"), __("Entry"), __("Type"), __("Principal"), __("Interest"), __("Amount")], rows) +
				`<p class="mb-1">${__("Deducted via Salary Slips")}</p>` +
				table([__("Period"), __("Salary Slip"), __("Principal"), __("Interest"), __("Total")], ded);
		});
	}

	// Employee advances
	html += table(
		[__("Advance"), __("Date"), __("Purpose"), __("Advance"), __("Paid"), __("Claimed"), __("Returned"), __("Pending"), __("Status")],
		(data.advances || []).map(
			(a) => `<tr><td>${frappe.utils.get_form_link("Employee Advance", a.name, true)}</td><td>${fdate(a.posting_date)}</td>
			<td>${esc(a.purpose || "")}</td><td>${fmt(a.advance_amount)}</td><td>${fmt(a.paid_amount)}</td>
			<td>${fmt(a.claimed_amount)}</td><td>${fmt(a.return_amount)}</td><td>${fmt(a.pending)}</td><td>${esc(a.status || "")}</td></tr>`
		)
	);
	return html;
}
