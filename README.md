SELECT 
    pi.posting_date AS posting_date,
    
    pii.item_name AS item_name,
    
    it.item_group AS item_group,
    
    pi.supplier AS supplier_name,
    
    pii.uom AS uom,
    pii.qty AS qty,
    pii.rate AS rate,
    pii.amount AS amount,

    pi.grand_total AS grand_total

FROM 
    `tabPurchase Invoice` pi

JOIN 
    `tabPurchase Invoice Item` pii 
        ON pi.name = pii.parent

LEFT JOIN 
    `tabItem` it 
        ON pii.item_code = it.name

WHERE 
    pi.docstatus = 1
    AND pi.posting_date BETWEEN %(from_date)s AND %(to_date)s
    AND pii.warehouse = %(warehouse)s

    -- 🔥 SMART ITEM GROUP FILTER
    AND (
        %(item_group)s IS NULL 
        OR %(item_group)s = '' 
        OR it.item_group = %(item_group)s
    )

ORDER BY 
    it.item_group, pi.posting_date DESC;