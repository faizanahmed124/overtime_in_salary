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
			const data = r.message || {};
			wrapper.$wrapper.html(build_html(data, frm.doc.salary_currency));
			bind_structure_editor(frm, wrapper.$wrapper, data.structure);
			sync_eobi(frm);
		},
	});
}

// Keeps the EOBI deduction row and the structure heading in line with the EOBI fields (display only).
function sync_eobi(frm) {
	const wrapper = frm.fields_dict.custom_salary_info_html;
	if (!wrapper) return;
	const $w = wrapper.$wrapper;
	const $body = $w.find(".ss-body");
	if (!$body.length) return;
	const on = cint(frm.doc.custom_eobi_applicable);
	const amount = flt(frm.doc.custom_eobi_amount);
	const $head = $w.find(".ss-heading");
	// edit the structure name in place: "... WITH EOBI" reads "... WITHOUT EOBI" when EOBI is off
	const $name = $head.find("b a").first().length ? $head.find("b a").first() : $head.find("b").first();
	if ($name.data("orig") === undefined) $name.data("orig", $name.text());
	const orig = $name.data("orig");
	$name.text(on ? orig : orig.replace(/\bWITH\s+EOBI\b/i, (m) => m.replace(/WITH/i, (w) => (w === w.toUpperCase() ? "WITHOUT" : "without"))));

	// rows already in the structure: show the employee's amount, hide when EOBI is off
	let has_row = false;
	$body.find("tr").not(".ss-eobi-virtual").each(function () {
		if (!/EOBI/i.test($(this).data("component") || "")) return;
		has_row = true;
		$(this).toggle(!!on);
		if (on && !$(this).find(".ss-is-formula").is(":checked")) $(this).find(".ss-amount").val(amount);
	});
	$body.find(".ss-eobi-virtual").remove();
	if (on && !has_row) {
		$body.append(`<tr class="ss-eobi-virtual"><td>Deduction</td><td>EOBI</td><td>EOBI</td>
			<td>${format_currency(amount, frm.doc.salary_currency)}</td><td></td><td>${__("No")}</td><td></td><td></td></tr>`);
	}
}

const API = "overtime_in_salary.overtime_in_salary.employee_salary_info.";

function component_row_html(c, options) {
	const esc = frappe.utils.escape_html;
	const is_new = !c.row_name;
	const name_cell = is_new
		? `<select class="form-control input-sm ss-component">${(options[c.type] || [])
				.map((o) => `<option value="${esc(o)}">${esc(o)}</option>`)
				.join("")}</select>`
		: esc(c.component);
	return `<tr data-row="${esc(c.row_name || "")}" data-type="${c.type}" data-component="${esc(c.component || "")}">
		<td>${c.type}</td>
		<td>${name_cell}</td>
		<td>${esc(c.abbr || "")}</td>
		<td style="min-width:240px">
			<label class="mb-1" style="font-weight:normal"><input type="checkbox" class="ss-is-formula" ${c.amount_based_on_formula ? "checked" : ""}> ${__("Formula")}</label>
			<input type="text" class="form-control input-sm ss-formula" value="${esc(c.formula || "")}" ${c.amount_based_on_formula ? "" : 'style="display:none"'}>
			<input type="number" step="any" class="form-control input-sm ss-amount" value="${c.amount || 0}" ${c.amount_based_on_formula ? 'style="display:none"' : ""}>
		</td>
		<td><input type="text" class="form-control input-sm ss-condition" value="${esc(c.condition || "")}"></td>
		<td>${c.depends_on_payment_days ? __("Yes") : __("No")}</td>
		<td class="text-center"><input type="checkbox" class="ss-no-total" ${c.do_not_include_in_total ? "checked" : ""}></td>
		<td class="text-center"><button type="button" class="btn btn-xs btn-danger ss-remove">&times;</button></td>
	</tr>`;
}

function bind_structure_editor(frm, $w, s) {
	$w.off(".ss"); // the wrapper survives re-renders; drop handlers from the previous render
	const $btn = $w.find(".ss-change-structure");
	$btn.on("click", () => change_structure(frm, s));
	if (!s) return;
	const $body = $w.find(".ss-body");
	const $save = $w.find(".ss-save");
	const dirty = () => $save.prop("disabled", false);

	$w.on("change.ss input.ss", ".ss-body input, .ss-body select", dirty);
	$w.on("change.ss", ".ss-is-formula", function () {
		const $tr = $(this).closest("tr");
		$tr.find(".ss-formula").toggle(this.checked);
		$tr.find(".ss-amount").toggle(!this.checked);
	});
	$w.on("click.ss", ".ss-remove", function () {
		const $tr = $(this).closest("tr");
		frappe.confirm(__("Are you sure you want to delete this row?"), () => {
			$tr.remove();
			dirty();
		});
	});
	$w.find(".ss-add").on("click", (e) => {
		const type = $(e.currentTarget).data("type");
		$body.append(component_row_html({ type, amount: 0 }, s.component_options));
		dirty();
	});
	$save.on("click", () => {
		const components = [];
		$body.find("tr").not(".ss-eobi-virtual").each(function () {
			const $tr = $(this);
			components.push({
				type: $tr.data("type"),
				row_name: $tr.data("row") || null,
				component: $tr.data("row") ? $tr.data("component") : $tr.find(".ss-component").val(),
				amount_based_on_formula: $tr.find(".ss-is-formula").is(":checked") ? 1 : 0,
				formula: $tr.find(".ss-formula").val(),
				amount: $tr.find(".ss-amount").val(),
				condition: $tr.find(".ss-condition").val(),
				do_not_include_in_total: $tr.find(".ss-no-total").is(":checked") ? 1 : 0,
			});
		});
		const run = () =>
			frappe.call({
				method: API + "save_salary_structure_components",
				args: { employee: frm.doc.name, salary_structure: s.salary_structure, modified: s.modified, components },
				freeze: true,
				freeze_message: __("Saving and validating salary calculation..."),
				callback() {
					frappe.show_alert({ message: __("Salary Structure saved"), indicator: "green" });
					render_salary_info(frm);
				},
			});
		run();
	});
}

function change_structure(frm, current) {
	const d = new frappe.ui.Dialog({
		title: __("Change Salary Structure"),
		fields: [
			{ fieldname: "salary_structure", fieldtype: "Link", options: "Salary Structure", label: __("Salary Structure"), reqd: 1,
				get_query: () => ({ filters: { docstatus: 1, is_active: "Yes", company: frm.doc.company } }) },
			{ fieldname: "from_date", fieldtype: "Date", label: __("From Date"), reqd: 1, default: frappe.datetime.get_today() },
		],
		primary_action_label: __("Assign"),
		primary_action(v) {
			frappe.call({
				method: API + "change_salary_structure",
				args: { employee: frm.doc.name, ...v },
				freeze: true,
				callback() {
					d.hide();
					frappe.show_alert({ message: __("Salary Structure assigned"), indicator: "green" });
					frm.reload_doc(); // EOBI fields follow the new structure; refresh re-renders the tables
				},
			});
		},
	});
	d.show();
}

function build_html(data, currency) {
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
	if (!s) {
		html += `<p class="text-muted">${__("No submitted Salary Structure Assignment is effective for this employee.")}</p>`;
	} else {
		html += `<p class="ss-heading"><b>${frappe.utils.get_form_link("Salary Structure", s.salary_structure, true)}</b>
			&middot; ${__("Assignment")} ${frappe.utils.get_form_link("Salary Structure Assignment", s.assignment, true)}</p>`;
		const options = s.component_options || {};
		html += `<div class="table-responsive"><table class="table table-bordered table-sm">
			<thead><tr>${[__("Type"), __("Component"), __("Abbr"), __("Amount / Formula"), __("Condition"), __("Depends on Payment Days"), __("Not in Total"), ""]
				.map((h) => `<th>${h}</th>`)
				.join("")}</tr></thead>
			<tbody class="ss-body">${s.components.map((c) => component_row_html(c, options)).join("")}</tbody></table></div>
			<div class="mb-3">
				<button type="button" class="btn btn-xs btn-default ss-add" data-type="Earning">${__("Add Earning")}</button>
				<button type="button" class="btn btn-xs btn-default ss-add" data-type="Deduction">${__("Add Deduction")}</button>
				<button type="button" class="btn btn-xs btn-primary ss-save" disabled>${__("Save Components")}</button>
			</div>`;
	}
	html += `<button type="button" class="btn btn-xs btn-default ss-change-structure mb-3">${__("Change Salary Structure")}</button>`;

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
