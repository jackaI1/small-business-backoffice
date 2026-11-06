// A terminal decision cannot be reopened. Each approval advances one review step.
return { form, action ->
    if (form.status == 'DRAFT') {
        if (action == 'submit') return 'PENDING'
        if (action == 'cancel') return 'CANCELLED'
    }
    if (form.status == 'PENDING') {
        if (action == 'approve') return form.step + 1 < form.route.size() ? 'PENDING' : 'APPROVED'
        if (action == 'reject') return 'REJECTED'
        if (action == 'cancel') return 'CANCELLED'
    }
    throw new IllegalArgumentException("Cannot ${action} a ${form.status} form")
}
