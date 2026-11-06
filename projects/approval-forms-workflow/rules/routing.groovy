// Amounts are exact decimals in CAD. The result is an ordered reviewer list.
return { form ->
    switch (form.type) {
        case 'purchase':
            if (form.amount <= 500G) return ['SUPERVISOR']
            if (form.amount <= 5000G) return ['MANAGER']
            return ['MANAGER', 'FINANCE']
        case 'expense':
            return form.amount <= 100G ? ['MANAGER'] : ['MANAGER', 'FINANCE']
        case 'access':
            if (form.amount != 0G) throw new IllegalArgumentException('Access requests must have a zero amount')
            return ['IT']
        default:
            throw new IllegalArgumentException("Unsupported form type: ${form.type}")
    }
}
