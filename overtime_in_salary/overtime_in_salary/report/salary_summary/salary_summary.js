frappe.query_reports["Salary Summary"] = {
    filters: [
        {
            fieldname: "company",
            label:     __("Company"),
            fieldtype: "Link",
            options:   "Company",
            default:   frappe.defaults.get_default("company"),
            reqd:      1,
        },
        {
            fieldname: "from_date",
            label:     __("From Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_start(),
            reqd:      1,
        },
        {
            fieldname: "to_date",
            label:     __("To Date"),
            fieldtype: "Date",
            default:   frappe.datetime.month_end(),
            reqd:      1,
        },
        {
            fieldname: "branch",
            label:     __("Branch"),
            fieldtype: "Link",
            options:   "Branch",
        },
        {
            fieldname: "mode_of_payment",
            label:     __("Mode of Payment"),
            fieldtype: "Link",
            options:   "Mode of Payment",
        },
        {
            fieldname: "department",
            label:     __("Department"),
            fieldtype: "Link",
            options:   "Department",
        },
    ],

    onload: function (report) {
        report.page.add_inner_button(__("🖨️ Print Report"), function () {
            let filters = report.get_values();
            let data    = report.data;

            if (!data || data.length === 0) {
                frappe.msgprint("No data to print. Please load the report first.");
                return;
            }

            // ── Helpers ──────────────────────────────────────────
            function strip(str) {
                return (str || "").replace(/<[^>]+>/g, "").trim();
            }

            function fmt(val) {
                if (!val && val !== 0) return "—";
                let n = parseFloat(val);
                if (!n) return "—";
                return "Rs " + n.toLocaleString("en-PK", {
                    minimumFractionDigits:  2,
                    maximumFractionDigits: 2,
                });
            }

            function fmtNum(val) {
                if (!val && val !== 0) return "—";
                let n = parseFloat(val);
                if (!n) return "—";
                return n.toLocaleString("en-PK", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }

            // ── Detect which optional columns have data ───────────
            let dataRows = data.filter(r => (r.department || "").indexOf("Grand Total") === -1);

            function colHasData(field) {
                return dataRows.some(r => parseFloat(r[field] || 0) !== 0);
            }

            // Build active column list dynamically
            let activeCols = [
                { key: "department",      label: "Department / Section", always: true,  fmt: "text"    },
                { key: "total_employees", label: "No. of Emp",           always: true,  fmt: "int"     },
                { key: "amount",          label: "Amount",               always: false, fmt: "currency" },
                { key: "ot_amount",       label: "OT.Amt",               always: false, fmt: "currency" },
                { key: "gross_salary",    label: "G.Salary",             always: false, fmt: "currency" },
                { key: "allowance",       label: "Allowance",            always: false, fmt: "currency" },
                { key: "eobi",            label: "EOBI",                 always: false, fmt: "currency" },
                { key: "income_tax",      label: "In.Tax",               always: false, fmt: "currency" },
                { key: "net_salary",      label: "Net Salary",           always: false, fmt: "currency" },
            ].filter(c => c.always || colHasData(c.key));

            // ── Build header row ──────────────────────────────────
            let thead_html = activeCols.map(c => {
                let align = c.fmt === "text" ? "" : ` class="right"`;
                return `<th${align}>${c.label}</th>`;
            }).join("");

            // ── Build data rows ───────────────────────────────────
            let rows_html = "";

            data.forEach(function (row, idx) {
                let dept     = row.department || "";
                let isGrand  = dept.indexOf("Grand Total") !== -1;

                let cells = activeCols.map(c => {
                    let val  = row[c.key];
                    let text = "";
                    if (c.fmt === "text")     text = strip(dept);
                    else if (c.fmt === "int") text = (val || 0);
                    else if (c.fmt === "currency") text = fmt(val);
                    else if (c.fmt === "num")      text = fmtNum(val);

                    let cls  = c.fmt === "text" ? "dept-cell" : "right";
                    if (c.key === "net_salary" && !isGrand) cls += " net-col";
                    if (c.key === "net_salary" &&  isGrand) cls  = "right golden";
                    return `<td class="${cls}">${text}</td>`;
                }).join("");

                let trClass = isGrand ? "grand-total-row" : (idx % 2 === 0 ? "even" : "odd");
                rows_html  += `<tr class="${trClass}">${cells}</tr>`;
            });

            // ── Meta ─────────────────────────────────────────────
            let company         = filters.company         || "";
            let from_date       = filters.from_date       || "";
            let to_date         = filters.to_date         || "";
            let branch          = filters.branch          || "All Branches";
            let mode_of_payment = filters.mode_of_payment || "All";
            let dept_filter     = filters.department      || "All Departments";
            let print_dt        = frappe.datetime.now_datetime();

            let html = `
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Salary Summary — ${company}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;900&family=DM+Sans:wght@300;400;500;600&display=swap');

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: 'DM Sans', sans-serif;
            background: #fff;
            color: #1a1a2e;
            padding: 36px 48px;
            font-size: 12px;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            border-bottom: 3px solid #1a1a2e;
            padding-bottom: 18px;
            margin-bottom: 22px;
        }

        .company-name {
            font-family: 'Playfair Display', serif;
            font-size: 26px;
            font-weight: 900;
            color: #1a1a2e;
        }

        .report-title {
            font-size: 11px;
            font-weight: 500;
            color: #666;
            letter-spacing: 3px;
            text-transform: uppercase;
            margin-top: 5px;
        }

        .header-right { text-align: right; }

        .badge {
            display: inline-block;
            background: #1a1a2e;
            color: #fff;
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            padding: 4px 14px;
            border-radius: 20px;
            margin-bottom: 10px;
        }

        .meta-grid {
            display: grid;
            grid-template-columns: auto auto;
            gap: 3px 16px;
        }

        .meta-label { font-size: 9px; color: #999; text-transform: uppercase; letter-spacing: 1px; text-align: right; }
        .meta-value { font-size: 11px; font-weight: 600; color: #1a1a2e; text-align: right; }

        .accent-bar {
            height: 4px;
            background: linear-gradient(90deg, #1a1a2e 0%, #4a90d9 50%, #e8c84a 100%);
            border-radius: 2px;
            margin-bottom: 24px;
        }

        table { width: 100%; border-collapse: collapse; font-size: 11.5px; }

        thead tr { background: #1a1a2e; color: #fff; }

        thead th {
            padding: 11px 10px;
            font-size: 9.5px;
            font-weight: 600;
            letter-spacing: 1.2px;
            text-transform: uppercase;
            white-space: nowrap;
        }

        thead th.right { text-align: right; }

        tbody tr.even { background: #f8f9fc; }
        tbody tr.odd  { background: #ffffff; }

        tbody td {
            padding: 10px 10px;
            border-bottom: 1px solid #eef0f5;
            color: #2d2d2d;
        }

        td.dept-cell { font-weight: 700; color: #1a1a2e; font-size: 12px; }
        td.right     { text-align: right; }
        td.net-col   { font-weight: 700; color: #1a5276; }

        tr.grand-total-row td {
            background: #1a1a2e !important;
            color: #fff !important;
            font-weight: 700;
            font-size: 12px;
            padding: 12px 10px;
            border: none;
        }

        tr.grand-total-row td.golden { color: #e8c84a !important; font-size: 13px; }

        .footer {
            margin-top: 36px;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-top: 1px solid #ddd;
            padding-top: 16px;
        }

        .note { font-size: 9px; color: #aaa; line-height: 1.8; }

        .signatures { display: flex; gap: 56px; }
        .sig-block  { text-align: center; }
        .sig-line   { width: 140px; border-top: 1.5px solid #1a1a2e; margin-bottom: 6px; }
        .sig-label  { font-size: 9px; color: #666; letter-spacing: 1px; text-transform: uppercase; }

        @media print {
            body  { padding: 15px 24px; }
            thead { display: table-header-group; }
        }
    </style>
</head>
<body>

    <div class="header">
        <div>
            <div class="company-name">${company}</div>
            <div class="report-title">Department Wise Salary Summary</div>
        </div>
        <div class="header-right">
            <div class="badge">Payroll Report</div>
            <div class="meta-grid">
                <span class="meta-label">Period</span>
                <span class="meta-value">${from_date} → ${to_date}</span>
                <span class="meta-label">Branch</span>
                <span class="meta-value">${branch}</span>
                <span class="meta-label">Mode</span>
                <span class="meta-value">${mode_of_payment}</span>
                <span class="meta-label">Department</span>
                <span class="meta-value">${dept_filter}</span>
                <span class="meta-label">Printed</span>
                <span class="meta-value">${print_dt}</span>
            </div>
        </div>
    </div>

    <div class="accent-bar"></div>

    <table>
        <thead><tr>${thead_html}</tr></thead>
        <tbody>${rows_html}</tbody>
    </table>

    <div class="footer">
        <div class="note">
            Generated: ${print_dt} &nbsp;|&nbsp; All amounts in PKR<br>
            Confidential — Internal Use Only
        </div>
        <div class="signatures">
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Prepared By</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Accounts</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">Audit</div></div>
            <div class="sig-block"><div class="sig-line"></div><div class="sig-label">General Manager</div></div>
        </div>
    </div>

</body>
</html>`;

            let w = window.open("", "_blank", "width=1100,height=750");
            w.document.write(html);
            w.document.close();
            w.focus();
            setTimeout(function () { w.print(); }, 800);
        });
    },
};